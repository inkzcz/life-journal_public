from uuid import UUID
from fastapi import APIRouter,Depends,Query,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from ..dependencies import db_dep,require_dynamic_blog
from ..tag_models import Tag,RecordTag,JournalTagIdentity
from ..services import tags as service
from ..services.archive import write_lock
from ..models import now
router=APIRouter(prefix='/api/admin/tags',dependencies=[Depends(require_dynamic_blog)])
class NameIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=200)
class MergeIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    target_id:UUID
    confirm:bool

@router.get('')
def listing(q:str=Query('',max_length=100),page:int=Query(1,ge=1,le=100000),db:Session=Depends(db_dep)):
    base=select(Tag).where(Tag.deleted_at.is_(None),Tag.merged_into.is_(None))
    if q.strip():base=base.where(Tag.normalized_name.icontains(service.normalize(q)[1],autoescape=True))
    total=db.scalar(select(func.count()).select_from(base.subquery()))
    rows=list(db.scalars(base.order_by(Tag.normalized_name,Tag.id).offset((page-1)*50).limit(50)))
    ids=[t.id for t in rows]
    rc=dict(db.execute(select(RecordTag.tag_id,func.count()).where(RecordTag.tag_id.in_(ids)).group_by(RecordTag.tag_id)).all())
    jc=dict(db.execute(select(JournalTagIdentity.tag_id,func.count(func.distinct(JournalTagIdentity.journal_id))).where(JournalTagIdentity.tag_id.in_(ids)).group_by(JournalTagIdentity.tag_id)).all())
    return {'items':[{'id':t.id,'name':t.name,'records':rc.get(t.id,0),'journals':jc.get(t.id,0)} for t in rows],'total':total,'page':page,'page_size':50}

@router.post('')
def create(data:NameIn,db:Session=Depends(db_dep)):
    write_lock(db);t=service.identity(db,data.name);db.commit();return {'id':t.id,'name':t.name}

@router.put('/{id}')
def rename(id:UUID,data:NameIn,db:Session=Depends(db_dep)):
    write_lock(db);t=service.active_tag(db,id);name,key=service.normalize(data.name)
    if db.scalar(select(Tag.id).where(Tag.normalized_name==key,Tag.id!=t.id)):raise HTTPException(409,'同名标签已存在，请明确执行合并')
    t.name=name;t.normalized_name=key;t.updated_at=now();db.commit();return {'id':t.id,'name':t.name}

@router.delete('/{id}')
def remove(id:UUID,db:Session=Depends(db_dep)):
    write_lock(db);t=service.active_tag(db,id)
    if any(service.counts(db,t.id).values()):raise HTTPException(409,'标签仍被引用，请先解除关联或合并')
    t.deleted_at=now();db.commit();return {'ok':True}

@router.post('/{id}/merge')
def merge(id:UUID,data:MergeIn,db:Session=Depends(db_dep),user=Depends(require_dynamic_blog)):
    if not data.confirm:raise HTTPException(422,'需要明确确认合并')
    result=service.merge(db,str(id),str(data.target_id),user.id);db.commit();return result

@router.get('/{id}/usage')
def usage(id:UUID,db:Session=Depends(db_dep)):
    from ..tag_models import RecordTag
    from ..content_models import ContentRecord
    import hashlib,json
    t=service.active_tag(db,id)
    records=[{'id':r.id,'title':r.title,'revision':r.revision,'deleted':bool(r.deleted_at)} for r in db.scalars(select(ContentRecord).join(RecordTag,RecordTag.record_id==ContentRecord.id).where(RecordTag.tag_id==t.id).order_by(ContentRecord.id))]
    stamp=hashlib.sha256(json.dumps([t.name,records],sort_keys=True).encode()).hexdigest()
    return {'id':t.id,'records':records,'count':len(records),'confirmation_token':stamp,'note':'仅解除当前关联；历史身份保留且不会在恢复时自动复活'}

class DeleteEverywhere(NameIn):
    confirmation_token:str

@router.post('/{id}/delete-everywhere')
def delete_everywhere(id:UUID,data:DeleteEverywhere,db:Session=Depends(db_dep),u=Depends(require_dynamic_blog)):
    from ..tag_models import RecordTag
    from ..content_models import ContentRecord
    from ..services.content import revision_snapshot
    from sqlalchemy import delete
    write_lock(db);t=service.active_tag(db,id);state=usage(id,db)
    if data.name!=t.name or data.confirmation_token!=state['confirmation_token']:raise HTTPException(409,'标签引用已变化，请重新查看并确认')
    records=list(db.scalars(select(ContentRecord).join(RecordTag,RecordTag.record_id==ContentRecord.id).where(RecordTag.tag_id==t.id)))
    db.execute(delete(RecordTag).where(RecordTag.tag_id==t.id));t.deleted_at=now()
    for r in records:r.revision+=1;r.updated_at=now();revision_snapshot(db,r,u.id)
    db.commit();return {'ok':True,'detached_records':len(records),'history_identity_retained':True}
