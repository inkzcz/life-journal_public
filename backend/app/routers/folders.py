import uuid
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select,func
from ..dependencies import db_dep,require_dynamic_blog
from ..archive_models import MediaFolder,MediaAsset
from ..archive_schemas import FolderIn,FolderEdit,MediaBatch
from ..content_schemas import DeleteIn
from ..services.archive import write_lock,asset,asset_data
from ..services.folders import folder_data,require_folder,validate_tree
from ..models import now
router=APIRouter(prefix='/api/admin/archive',dependencies=[Depends(require_dynamic_blog)])

@router.get('/folders')
def folders(db=Depends(db_dep)):
    return [folder_data(r) for r in db.scalars(select(MediaFolder).order_by(MediaFolder.normalized_name,MediaFolder.id))]

@router.post('/folders')
def create(data:FolderIn,db=Depends(db_dep)):
    write_lock(db);id=str(uuid.uuid4());normalized=validate_tree(db,id,data.parent_id,data.name)
    row=MediaFolder(id=id,name=data.name,normalized_name=normalized,parent_id=str(data.parent_id) if data.parent_id else None)
    db.add(row);db.commit();return folder_data(row)

@router.put('/folders/{id}')
def edit(id:UUID,data:FolderEdit,db=Depends(db_dep)):
    write_lock(db);row=require_folder(db,id)
    if row.revision!=data.expected_revision:raise HTTPException(409,'文件夹已更新，请重新读取')
    row.normalized_name=validate_tree(db,row.id,data.parent_id,data.name)
    row.name=data.name;row.parent_id=str(data.parent_id) if data.parent_id else None;row.revision+=1;row.updated_at=now();db.commit();return folder_data(row)

@router.delete('/folders/{id}')
def remove(id:UUID,data:DeleteIn,db=Depends(db_dep)):
    write_lock(db);row=require_folder(db,id)
    if row.revision!=data.expected_revision:raise HTTPException(409,'文件夹已更新')
    if db.scalar(select(MediaFolder.id).where(MediaFolder.parent_id==row.id).limit(1)) or db.scalar(select(MediaAsset.id).where(MediaAsset.folder_id==row.id).limit(1)):raise HTTPException(409,'只能删除空文件夹；请先移动子文件夹及所有图片（含回收站）')
    from ..v5_models import RecordMediaFolder,MediaArchiveRule
    if db.scalar(select(RecordMediaFolder.record_id).where(RecordMediaFolder.folder_id==row.id)) or db.scalar(select(MediaArchiveRule.id).where(MediaArchiveRule.parent_id==row.id)):raise HTTPException(409,'文件夹仍绑定文章或归档规则，不能删除；请先明确替换绑定或规则目标')
    db.delete(row);db.commit();return {'ok':True}

@router.post('/media-batch')
def batch(data:MediaBatch,db=Depends(db_dep)):
    write_lock(db)
    if data.action=='move':require_folder(db,data.folder_id)
    rows=[];blocked=[]
    for item in sorted(data.items,key=lambda i:str(i.id)):
        try:
            m=asset(db,item.id)
            if m.revision!=item.expected_revision:raise HTTPException(409,'图片已更新')
            if data.action=='trash':
                from ..routers.archive import check_media_unused
                check_media_unused(db,m)
            rows.append(m)
        except HTTPException as e:blocked.append({'id':str(item.id),'reason':e.detail})
    if blocked:raise HTTPException(409,{'message':'整批未执行，请排除受阻项后重新确认','blocked':blocked})
    for m in rows:
        if data.action=='move':m.folder_id=str(data.folder_id) if data.folder_id else None
        elif data.action=='category':m.category=data.category
        else:m.deleted_at=now()
        m.revision+=1
    db.commit();return {'items':[asset_data(m) for m in rows],'state':'completed'}
