from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field
from sqlalchemy import select
from ..dependencies import db_dep,require_dynamic_blog
from ..archive_schemas import StrictModel
from ..services.content import get_record
from ..services.life import life_data
from ..services.itinerary import extract,fingerprint
from ..life_models import TripActivity
router=APIRouter(prefix='/api/admin/content/records',dependencies=[Depends(require_dynamic_blog)])
class Preview(StrictModel):
    expected_revision:int=Field(ge=1)
    body:str=Field(max_length=300000)
class Confirm(Preview):
    body_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    selected:list[str]=Field(min_length=1,max_length=300)

def preview_data(db,id,data):
    r=get_record(db,id)
    if r.revision!=data.expected_revision or r.body!=data.body:raise HTTPException(409,'正文或修订已变化，请先保存文章，再重新提取预览；本地输入保留')
    life=life_data(db,r.id)
    from datetime import date
    result=extract(r.body,date.fromisoformat(life['start_date']) if life['start_date'] else None,date.fromisoformat(life['end_date']) if life['end_date'] else None)
    seen=set(db.scalars(select(TripActivity.source_key).where(TripActivity.record_id==r.id,TripActivity.source_key.is_not(None))))
    # Scope IDs to the record, preserving deterministic identity on response retry.
    import uuid
    for item in result['items']:item['id']=str(uuid.uuid5(uuid.UUID(r.id),item['source_key']))
    result['items']=[i for i in result['items'] if i['source_key'] not in seen]
    return result|{'revision':r.revision}
@router.post('/{id}/itinerary-preview')
def preview(id:UUID,data:Preview,db=Depends(db_dep)):return preview_data(db,id,data)
@router.post('/{id}/itinerary-confirm')
def confirm(id:UUID,data:Confirm,db=Depends(db_dep)):
    from ..services.archive import write_lock
    write_lock(db);result=preview_data(db,id,data)
    if result['body_hash']!=data.body_hash:raise HTTPException(409,'提取预览已过期，请重新提取')
    rows={x['source_key']:x for x in result['items']}
    if len(set(data.selected))!=len(data.selected) or not set(data.selected)<=set(rows):raise HTTPException(409,'所选活动已变化或已同步，请重新预览')
    return {'items':[{k:v for k,v in rows[key].items() if k!='line'} for key in data.selected],'note':'仅追加到本地编辑草稿；使用现有保存/冲突保护提交，不自动发布'}

class Reconcile(StrictModel):
    expected_revision:int=Field(ge=1)
    body_hash:str=Field(pattern=r'^[a-f0-9]{64}$')

@router.post('/{id}/itinerary-sync-preview')
def sync_preview(id:UUID,data:Preview,db=Depends(db_dep)):
    from ..services.itinerary_generation import proposal
    r=get_record(db,id)
    if r.revision!=data.expected_revision or r.body!=data.body:raise HTTPException(409,'请先保存正文后重新预览差异')
    return proposal(db,r)

@router.post('/{id}/itinerary-sync-confirm')
def sync_confirm(id:UUID,data:Reconcile,db=Depends(db_dep),user=Depends(require_dynamic_blog)):
    from ..services.archive import write_lock
    from ..services.itinerary_generation import apply
    from ..services.content import record_data
    write_lock(db);r=get_record(db,id)
    r=apply(db,r,data.model_dump(),user.id);db.commit()
    return record_data(db,r)
