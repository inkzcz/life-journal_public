from typing import Literal
from uuid import UUID
import uuid
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field
from sqlalchemy import select,delete
from ..dependencies import db_dep,require_dynamic_blog
from ..content_schemas import StrictModel
from ..archive_schemas import BatchItem
from ..v5_models import MediaArchiveRule,MediaArchivePlan,RecordMediaFolder
from ..services.archive import write_lock,asset,asset_data
from ..services.organization import preview,execute,article_folder
from ..services.folders import require_folder
from ..models import now
router=APIRouter(prefix='/api/admin/organization',dependencies=[Depends(require_dynamic_blog)])
class RuleIn(StrictModel):
    name:str=Field(min_length=1,max_length=100)
    enabled:bool=False
    date_source:Literal['uploaded','captured']='uploaded'
    fallback:Literal['uploaded','unknown']='unknown'
    granularity:Literal['year','month','day']='month'
    by_type:bool=False
    parent_id:UUID|None=None
    expected_revision:int|None=Field(None,ge=1)
class Items(StrictModel):
    items:list[BatchItem]=Field(min_length=1,max_length=100)
class Execute(StrictModel):
    confirmation:Literal['确认逻辑归档']
class Batch(Items):
    action:Literal['unfile','trash']
    confirmation:Literal['逐项处理图片']
def data(r):return {k:getattr(r,k) for k in ['id','name','enabled','date_source','fallback','granularity','by_type','parent_id','revision']}
@router.get('/rules')
def rules(db=Depends(db_dep)):return [data(r) for r in db.scalars(select(MediaArchiveRule).order_by(MediaArchiveRule.id))]
@router.post('/rules')
def create(d:RuleIn,db=Depends(db_dep),u=Depends(require_dynamic_blog)):
    write_lock(db);require_folder(db,d.parent_id)
    if d.enabled and db.scalar(select(MediaArchiveRule.id).where(MediaArchiveRule.enabled.is_(True)).limit(1)):raise HTTPException(409,'一次只启用一条新上传规则，请先停用原规则')
    r=MediaArchiveRule(id=str(uuid.uuid4()),created_by=u.id,**d.model_dump(exclude={'expected_revision','parent_id'}),parent_id=str(d.parent_id) if d.parent_id else None)
    db.add(r);db.commit();return data(r)
@router.put('/rules/{id}')
def edit(id:UUID,d:RuleIn,db=Depends(db_dep)):
    write_lock(db);r=db.get(MediaArchiveRule,str(id))
    if not r:raise HTTPException(404,'规则不存在')
    if r.revision!=d.expected_revision:raise HTTPException(409,'规则已更新')
    require_folder(db,d.parent_id)
    if d.enabled and db.scalar(select(MediaArchiveRule.id).where(MediaArchiveRule.enabled.is_(True),MediaArchiveRule.id!=r.id).limit(1)):raise HTTPException(409,'请先停用其他新上传规则')
    for k,v in d.model_dump(exclude={'expected_revision','parent_id'}).items():setattr(r,k,v)
    r.parent_id=str(d.parent_id) if d.parent_id else None;r.revision+=1;db.commit();return data(r)
@router.post('/rules/{id}/preview')
def plan(id:UUID,d:Items,db=Depends(db_dep),u=Depends(require_dynamic_blog)):
    write_lock(db);r=db.get(MediaArchiveRule,str(id))
    if not r:raise HTTPException(404,'规则不存在')
    if len({x.id for x in d.items})!=len(d.items):raise HTTPException(422,'图片不能重复')
    p=preview(db,r,d.items,u.id);db.commit();return {'id':p.id,'items':p.items,'enabled':r.enabled}
@router.post('/plans/{id}/execute')
def apply(id:UUID,d:Execute,db=Depends(db_dep),u=Depends(require_dynamic_blog)):
    write_lock(db);p=db.get(MediaArchivePlan,str(id))
    if not p:raise HTTPException(404,'归档预览不存在')
    r=db.get(MediaArchiveRule,p.rule_id)
    if not p.completed and not r.enabled:raise HTTPException(409,'请先明确启用归档规则，再重新预览')
    out=execute(db,p,u.id);db.commit();return out
@router.post('/media-actions')
def batch(d:Batch,db=Depends(db_dep)):
    if len({x.id for x in d.items})!=len(d.items):raise HTTPException(422,'图片不能重复')
    result=[]
    for item in d.items:
        try:
            write_lock(db);m=asset(db,item.id)
            if m.revision!=item.expected_revision:raise HTTPException(409,'图片已更新')
            if d.action=='trash':
                from .archive import check_media_unused
                check_media_unused(db,m);m.deleted_at=now()
            else:m.folder_id=None
            m.revision+=1;db.commit();result.append({'id':m.id,'state':'completed','revision':m.revision})
        except HTTPException as e:db.rollback();result.append({'id':str(item.id),'state':'blocked','reason':e.detail})
        except Exception:db.rollback();result.append({'id':str(item.id),'state':'failed','reason':'事务失败，未标记成功，可重新读取后重试'})
    return {'items':result}
