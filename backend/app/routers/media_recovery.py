import uuid
from uuid import UUID
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import FileResponse
from pydantic import Field,model_validator
from sqlalchemy import select
from sqlalchemy.orm import undefer_group
from ..archive_schemas import StrictModel,BatchItem
from ..archive_models import MediaAsset,MediaPurgeOperation
from ..dependencies import db_dep,require_dynamic_blog,get_settings
from ..services.archive import asset_data
from ..services.resource_usage import media_usage
from ..services.media_recovery import purge_media,restore_media,resume,operation_data,safe
from ..routers.archive import page_result
router=APIRouter(prefix='/api/admin/archive',dependencies=[Depends(require_dynamic_blog)])
class Action(StrictModel):
    items:list[BatchItem]=Field(min_length=1,max_length=100)
    action:Literal['restore','purge']
    request_key:UUID
    confirmation:Literal['恢复图片','永久删除图片']
    confirm_count:int=Field(ge=1,le=100)
    @model_validator(mode='after')
    def valid(self):
        if len(set(i.id for i in self.items))!=len(self.items) or self.confirm_count!=len(self.items):raise ValueError('必须确认实际图片数量且不能重复')
        if self.confirmation!=('恢复图片' if self.action=='restore' else '永久删除图片'):raise ValueError('请确认操作')
        return self
class Resume(StrictModel):
    action:Literal['retry','cancel']
    confirmation:Literal['继续永久删除','取消删除']
    @model_validator(mode='after')
    def valid(self):
        if self.confirmation!=('继续永久删除' if self.action=='retry' else '取消删除'):raise ValueError('请确认操作')
        return self

@router.get('/media-trash')
def trash(page:int=Query(1,ge=1),page_size:int=Query(24,ge=1,le=100),db=Depends(db_dep)):
    return page_result(db,select(MediaAsset).options(undefer_group('media_management')).where(MediaAsset.deleted_at.is_not(None)),page,page_size,lambda m:{**asset_data(m),'deleted_at':m.deleted_at.isoformat(),'purge_operation_id':m.purge_operation_id},[MediaAsset.deleted_at.desc(),MediaAsset.id])

@router.get('/media-trash/{id}')
def detail(id:UUID,db=Depends(db_dep)):
    m=db.get(MediaAsset,str(id))
    if not m or m.deleted_at is None:raise HTTPException(404,'回收站图片不存在')
    return {**asset_data(m),'purge_operation_id':m.purge_operation_id,'references':media_usage(db,m.id)}

@router.get('/media-trash/{id}/preview')
def preview(id:UUID,db=Depends(db_dep),settings=Depends(get_settings)):
    m=db.get(MediaAsset,str(id))
    if not m or m.deleted_at is None or m.purge_operation_id:raise HTTPException(404,'图片不可预览')
    path=safe(settings.media_dir/'library-v1'/m.id/'preview.webp')
    if not path.is_file():raise HTTPException(404,'预览不存在')
    return FileResponse(path,media_type='image/webp',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; sandbox"})

@router.post('/media-trash/actions')
def actions(data:Action,db=Depends(db_dep),user=Depends(require_dynamic_blog),settings=Depends(get_settings)):
    results=[]
    for item in data.items:
        try:
            if data.action=='restore':r=restore_media(db,str(item.id),item.expected_revision,settings.media_dir)
            else:r=purge_media(db,str(item.id),item.expected_revision,user.id,str(uuid.uuid5(data.request_key,str(item.id))),settings.media_dir)
            results.append({'media_id':str(item.id),**r})
        except Exception as e:
            db.rollback()
            code=e.detail if isinstance(e,HTTPException) else '文件或数据库操作失败，未标记完成；请查看操作日志后重试'
            op=db.scalar(select(MediaPurgeOperation).where(MediaPurgeOperation.actor_id==user.id,MediaPurgeOperation.request_key==str(uuid.uuid5(data.request_key,str(item.id)))))
            if op:op.error_code='operation_interrupted';db.commit()
            results.append({'media_id':str(item.id),'state':'blocked' if not op else op.state,'reason':code,'operation_id':op.id if op else None})
    return {'items':results,'note':'仅completed表示文件已实际清理；已有备份不会因本次删除而清除'}

@router.get('/media-purge-operations')
def operations(page:int=Query(1,ge=1,le=1000000),db=Depends(db_dep)):
    return [operation_data(o) for o in db.scalars(select(MediaPurgeOperation).order_by(MediaPurgeOperation.created_at.desc(),MediaPurgeOperation.id).offset((page-1)*100).limit(100))]

@router.post('/media-purge-operations/{id}')
def retry(id:UUID,data:Resume,db=Depends(db_dep),settings=Depends(get_settings)):
    try:return resume(db,str(id),settings.media_dir,cancel=data.action=='cancel')
    except HTTPException:db.rollback();raise
    except Exception:
        db.rollback();raise HTTPException(409,'操作未完成，日志与文件已保留，请核对后重试') from None
