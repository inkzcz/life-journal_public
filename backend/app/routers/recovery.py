"""Unified recovery and history are Admin-only and dynamically gated."""
import uuid
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import select,func
from sqlalchemy.orm import defer
from ..dependencies import db_dep,require_dynamic_blog,get_settings
from ..content_models import ContentRecord,RecordRevision
from ..archive_models import MediaAsset
from ..recovery_schemas import TrashBatch,HistoryRestore,RevisionIn
from ..services.archive import write_lock,asset_data
from ..services.content import record_data,get_record,record_summaries
from ..services.recovery import warnings,restore_trash,purge,revision_data,restore_history,check_revision
router=APIRouter(prefix='/api/admin/recovery',dependencies=[Depends(require_dynamic_blog)])

@router.get('/trash')
def trash(page:int=Query(1,ge=1,le=1000000),page_size:int=Query(20,ge=1,le=100),q:str=Query('',max_length=200),type_id:UUID|None=None,db=Depends(db_dep)):
    query=select(ContentRecord).where(ContentRecord.deleted_at.is_not(None))
    if q:query=query.where(ContentRecord.title.icontains(q,autoescape=True))
    if type_id:query=query.where(ContentRecord.type_id==str(type_id))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    items=record_summaries(db,query.order_by(ContentRecord.deleted_at.desc(),ContentRecord.id).offset((page-1)*page_size).limit(page_size))
    return {'items':items,'total':total,'page':page,'page_size':page_size}

@router.get('/trash/{id}')
def deleted_record(id:UUID,db=Depends(db_dep)):
    r=db.get(ContentRecord,str(id))
    if not r or r.deleted_at is None:raise HTTPException(404,'回收记录不存在')
    return {**record_data(db,r),'warnings':warnings(db,r)}

@router.post('/trash/{action}')
def batch(action:str,data:TrashBatch,db=Depends(db_dep),actor=Depends(require_dynamic_blog)):
    if action not in {'restore','purge'}:raise HTTPException(404,'操作不存在')
    if data.confirmation!=('恢复' if action=='restore' else '永久删除'):raise HTTPException(422,'操作确认不匹配')
    write_lock(db);results=[]
    for item in data.items:
        try:
            with db.begin_nested():
                r=db.get(ContentRecord,str(item.id))
                if not r:
                    if action=='restore':raise HTTPException(404,'记录已永久删除')
                    result={'id':str(item.id),'state':'already_purged'}
                elif action=='restore':result=restore_trash(db,r,actor.id,item.expected_revision)
                else:purge(db,r,item.expected_revision);result={'id':str(item.id),'state':'purged'}
            results.append(result)
        except HTTPException as e:results.append({'id':str(item.id),'state':'failed','status':e.status_code,'error':e.detail})
        except Exception:results.append({'id':str(item.id),'state':'failed','status':409,'error':'引用约束冲突，此条已回滚'})
    db.commit();return {'items':results}

@router.get('/history/{id}')
def history(id:UUID,page:int=Query(1,ge=1),db=Depends(db_dep)):
    r=db.get(ContentRecord,str(id))
    if not r:raise HTTPException(404,'记录不存在')
    query=select(RecordRevision).where(RecordRevision.record_id==str(id))
    return {'current':record_data(db,r,marker_protocol=False),'items':[{'number':v.number,'created_at':v.created_at.isoformat()} for v in db.scalars(query.options(defer(RecordRevision.snapshot)).order_by(RecordRevision.number.desc()).offset((page-1)*20).limit(20))],
            'total':db.scalar(select(func.count()).select_from(query.subquery()))}

@router.get('/history/{id}/{number}')
def version(id:UUID,number:int,db=Depends(db_dep)):
    row=db.get(RecordRevision,(str(id),number))
    if not row:raise HTTPException(404,'历史版本不存在')
    return revision_data(row)

@router.post('/history/{id}/{number}/restore')
def restore_version(id:UUID,number:int,data:HistoryRestore,db=Depends(db_dep),actor=Depends(require_dynamic_blog)):
    write_lock(db);r=get_record(db,id);row=db.get(RecordRevision,(str(id),number))
    if not row:raise HTTPException(404,'历史版本不存在')
    result=restore_history(db,r,row,data,actor.id);db.commit();return result

@router.get('/media')
def deleted_media(db=Depends(db_dep),page:int=Query(1,ge=1)):
    rows=db.scalars(select(MediaAsset).where(MediaAsset.deleted_at.is_not(None)).order_by(MediaAsset.deleted_at.desc(),MediaAsset.id).offset((page-1)*20).limit(20))
    return [asset_data(m)|{'deleted_at':m.deleted_at.isoformat()} for m in rows]

@router.post('/media/{id}/restore')
def restore_media(id:UUID,data:RevisionIn,db=Depends(db_dep),settings=Depends(get_settings)):
    from ..services.media_recovery import restore_media as recover
    recover(db,str(id),data.expected_revision,settings.media_dir)
    return asset_data(db.get(MediaAsset,str(id)))
