import io, uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse,Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from PIL import Image, UnidentifiedImageError
from app.dependencies import db_dep, current_user, require_admin, get_settings
from app.models import User, Media
from .service import get_journal

from .image_preview import legacy_preview

router = APIRouter()

@router.get('/api/journals/{id}/media')
def list_media(id:int,db:DBSession=Depends(db_dep),user:User=Depends(current_user)):
    get_journal(id,db)
    return [{'id':m.id,'filename':m.filename} for m in db.scalars(select(Media).where(Media.journal_id==id)).all()]

@router.post('/api/journals/{id}/media')
async def upload_media(id:int,file:UploadFile=File(...),db:DBSession=Depends(db_dep),user:User=Depends(require_admin),settings=Depends(get_settings)):
    get_journal(id,db)
    data=await file.read(10*1024*1024+1)
    if len(data)>10*1024*1024:raise HTTPException(413,'单张照片不能超过10MB')
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            if img.format not in ('JPEG','PNG','WEBP'):raise ValueError('格式不支持')
            if img.width*img.height>50_000_000:raise ValueError('像素数量过大')
            mime={'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp'}[img.format]
    except (UnidentifiedImageError,Image.DecompressionBombError,ValueError,OSError) as exc:
        raise HTTPException(415,'仅支持有效的 JPEG、PNG、WebP 图片') from exc
    mid=str(uuid.uuid4())
    preview=legacy_preview(data)
    folder=settings.media_dir/'legacy-previews-v1';folder.mkdir(parents=True,exist_ok=True)
    try:
        (settings.media_dir/mid).write_bytes(data)
        (folder/(mid+'.webp')).write_bytes(preview)
    except Exception:
        (settings.media_dir/mid).unlink(missing_ok=True)
        (folder/(mid+'.webp')).unlink(missing_ok=True)
        raise
    db.add(Media(id=mid,journal_id=id,filename=(file.filename or 'photo')[:255],mime_type=mime))
    try:
        db.commit()
    except Exception:
        db.rollback()
        (settings.media_dir/mid).unlink(missing_ok=True)
        (folder/(mid+'.webp')).unlink(missing_ok=True)
        raise
    return {'id':mid}

@router.get('/api/media/{id}')
def get_media(id:str,db:DBSession=Depends(db_dep),user:User=Depends(current_user),settings=Depends(get_settings)):
    m=db.get(Media,id)
    if not m:raise HTTPException(404,'照片不存在')
    path=settings.media_dir/m.id
    if not path.is_file():raise HTTPException(404,'照片文件不存在')
    return FileResponse(path,media_type=m.mime_type,headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


@router.get('/api/media/{id}/preview')
def preview_media(id:str,db:DBSession=Depends(db_dep),user:User=Depends(current_user),settings=Depends(get_settings)):
    m=db.get(Media,id)
    if not m:raise HTTPException(404,'照片不存在')
    path=settings.media_dir/'legacy-previews-v1'/(m.id+'.webp')
    headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; sandbox"}
    if path.is_file():return FileResponse(path,media_type='image/webp',headers=headers)
    original=settings.media_dir/m.id
    if not original.is_file():raise HTTPException(404,'照片文件不存在')
    # Pre-existing images remain readable without mutating backed-up files on GET.
    if original.stat().st_size>10*1024*1024:raise HTTPException(413,'原文件超出预览限制')
    return Response(legacy_preview(original.read_bytes()),media_type='image/webp',headers=headers)
