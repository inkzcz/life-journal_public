"""Private independent images and provider-neutral places."""
import hashlib
import io
import re
import shutil
import uuid
import warnings
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Header, Form
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select, func, or_
from sqlalchemy.orm import undefer_group
from datetime import date,datetime,time,timezone
from ..dependencies import db_dep, require_dynamic_blog, current_user, require_admin, get_settings
from ..models import now
from ..archive_models import MediaAsset, Place, RecordMedia, RecordPlace
from ..content_models import ContentRecord
from ..archive_schemas import AssetEdit, PlaceIn, PlaceEdit
from ..content_schemas import DeleteIn
from ..services.archive import asset, place, asset_data, place_data, record_ref, write_lock

router=APIRouter()
admin=APIRouter(prefix='/api/admin/archive',dependencies=[Depends(require_dynamic_blog)])

def page_result(db,query,page,page_size,serializer,ordering):
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    items=db.scalars(query.order_by(*ordering).offset((page-1)*page_size).limit(page_size))
    return {'items':[serializer(x) for x in items],'total':total,'page':page,'page_size':page_size}

def search(value):
    return '%'+value.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'

def revision(resource,expected):
    if resource.revision!=expected:raise HTTPException(409,'数据已被其他页面修改，请重新读取；未保存输入会保留')

@admin.get('/media')
def list_assets(page:int=Query(1,ge=1),page_size:int=Query(24,ge=1,le=100),q:str=Query('',max_length=200),folder_id:UUID|None=None,unfiled:bool=False,uploaded_from:date|None=None,uploaded_to:date|None=None,db=Depends(db_dep)):
    query=select(MediaAsset).options(undefer_group('media_management')).where(MediaAsset.deleted_at.is_(None))
    if folder_id:query=query.where(MediaAsset.folder_id==str(folder_id))
    if unfiled:query=query.where(MediaAsset.folder_id.is_(None))
    if uploaded_from:query=query.where(MediaAsset.created_at>=datetime.combine(uploaded_from,time.min,timezone.utc))
    if uploaded_to:query=query.where(MediaAsset.created_at<=datetime.combine(uploaded_to,time.max,timezone.utc))
    if q:query=query.where(or_(MediaAsset.title.ilike(search(q),escape='\\'),MediaAsset.filename.ilike(search(q),escape='\\')))
    return page_result(db,query,page,page_size,asset_data,[MediaAsset.created_at.desc(),MediaAsset.id])

@admin.post('/media')
async def upload(file:UploadFile=File(...),db=Depends(db_dep),user=Depends(require_dynamic_blog),settings=Depends(get_settings),upload_key:str|None=Header(None,alias='X-Upload-Key'),folder_id:UUID|None=Form(None),auto_archive:bool=Form(True)):
    data=await file.read(10*1024*1024+1)
    if len(data)>10*1024*1024:raise HTTPException(413,'单张图片最多10MB')
    from ..services.image_upload import prepare_image
    from ..services.uploads import save_upload
    files,metadata=prepare_image(data,file.filename)
    return save_upload(db,user,settings,upload_key,files,metadata,folder_id=folder_id,auto_archive=auto_archive)

@admin.get('/media/{id}')
def read_asset(id:UUID,db=Depends(db_dep)):
    m=asset(db,id)
    from ..services.resource_usage import media_usage
    usages=media_usage(db,m.id)
    references=[];seen=set()
    for u in usages:
        if u['id'] not in seen:
            references.append({**u,**({'historical':True} if u['kind']!='画廊/封面' else {})});seen.add(u['id'])
    return {**asset_data(m),'references':references,'usages':usages}

@admin.put('/media/{id}')
def edit_asset(id:UUID,data:AssetEdit,db=Depends(db_dep)):
    write_lock(db);m=asset(db,id);revision(m,data.expected_revision)
    for k,v in data.model_dump(exclude={'expected_revision'},exclude_none=True).items():setattr(m,k,v)
    m.revision+=1;db.commit();return asset_data(m)

@admin.delete('/media/{id}')
def remove_asset(id:UUID,data:DeleteIn,db=Depends(db_dep)):
    write_lock(db);m=asset(db,id);revision(m,data.expected_revision)
    check_media_unused(db,m)
    m.deleted_at=now();m.revision+=1;db.commit()
    return {'ok':True}  # Soft delete retains files; explicit audited purge lives in media_recovery.

@router.get('/api/library-media/{id}/{variant}')
def private_file(id:UUID,variant:str,db=Depends(db_dep),user=Depends(current_user),settings=Depends(get_settings)):
    if variant not in {'thumbnail','preview','original'}:raise HTTPException(404,'文件不存在')
    if variant=='original':require_admin(user,db)
    m=asset(db,id)
    filename='original' if variant=='original' else ('thumbnail.webp' if variant=='thumbnail' and m.thumbnail_sha256 else 'preview.webp')
    path=settings.media_dir/'library-v1'/m.id/filename
    if not path.is_file():raise HTTPException(404,'文件不存在')
    # Generated download name avoids trusting the uploaded filename in headers.
    extension={'image/jpeg':'jpg','image/png':'png','image/webp':'webp'}[m.mime_type]
    headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; sandbox"}
    return FileResponse(path,media_type=m.mime_type if variant=='original' else 'image/webp',headers=headers,
                        filename=m.id+'.'+extension if variant=='original' else None)

@admin.get('/places')
def list_places(page:int=Query(1,ge=1),page_size:int=Query(24,ge=1,le=100),q:str=Query('',max_length=200),db=Depends(db_dep)):
    query=select(Place)
    if q:query=query.where(or_(*[c.ilike(search(q),escape='\\') for c in [Place.name,Place.city,Place.address,Place.category]]))
    return page_result(db,query,page,page_size,place_data,[Place.updated_at.desc(),Place.id])

@admin.post('/places')
def create_place(data:PlaceIn,db=Depends(db_dep)):
    write_lock(db);p=Place(id=str(uuid.uuid4()),**data.model_dump());db.add(p);db.commit();return place_data(p)

@admin.get('/places/{id}')
def read_place(id:UUID,db=Depends(db_dep)):
    p=place(db,id)
    from ..services.places import usages
    from ..archive_models import PlaceAlias
    alias=db.get(PlaceAlias,p.id)
    refs=usages(db,p.id)
    return {**place_data(p),'references':list({u['id']:u for u in refs}.values()),'usages':refs,'merged_into':alias.target_id if alias else None}

@admin.put('/places/{id}')
def edit_place(id:UUID,data:PlaceEdit,db=Depends(db_dep)):
    write_lock(db);p=place(db,id);revision(p,data.expected_revision)
    from ..archive_models import PlaceAlias
    if db.get(PlaceAlias,p.id):raise HTTPException(409,'合并后的历史身份不可重新编辑或启用，请编辑目标地点')
    for k,v in data.model_dump(exclude={'expected_revision'}).items():setattr(p,k,v)
    p.revision+=1;p.updated_at=now();db.commit();return place_data(p)

router.include_router(admin)


def check_media_unused(db,m):
    from ..services.resource_usage import assert_media_unused
    assert_media_unused(db,m.id)
