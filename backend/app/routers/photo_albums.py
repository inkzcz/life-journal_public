import uuid
from uuid import UUID
from typing import Literal
from pydantic import Field,model_validator
from fastapi import APIRouter,Depends,Query,HTTPException
from sqlalchemy import select,delete
from ..dependencies import current_user,require_dynamic_blog,db_dep
from ..archive_models import MediaAsset
from ..album_models import Album,AlbumPhoto
from ..content_schemas import StrictModel
from ..services.archive import write_lock
from ..services.photo_stream import stream,visible_refs
router=APIRouter(prefix='/api/photos',dependencies=[Depends(current_user)])
admin=APIRouter(prefix='/api/admin/photo-albums',dependencies=[Depends(require_dynamic_blog)])

@router.get('')
def photos(page:int=Query(1,ge=1,le=100000),year:int|None=Query(None,ge=1,le=9999),month:int|None=Query(None,ge=1,le=12),record_id:UUID|None=None,place_id:UUID|None=None,kind:Literal['l','f','m','s','g','t']|None=None,album_id:UUID|None=None,db=Depends(db_dep)):
    return stream(db,page=page,year=year,month=month,record_id=record_id,place_id=place_id,kind=kind,album_id=album_id)

@router.get('/albums')
def albums(db=Depends(db_dep)):
    q=visible_refs()
    visible=set(db.scalars(q.with_only_columns(q.selected_columns.media_id)))
    return [{'id':a.id,'name':a.name,'revision':a.revision,'cover_id':a.cover_id if a.cover_id in visible else None} for a in db.scalars(select(Album).order_by(Album.name,Album.id))]

class AlbumIn(StrictModel):
    name:str=Field(min_length=1,max_length=200)
    media_ids:list[UUID]=Field(default_factory=list,max_length=500)
    cover_id:UUID|None=None
    expected_revision:int=Field(0,ge=0)
    @model_validator(mode='after')
    def check(self):
        if not self.name.strip():raise ValueError('请填写相册名称')
        if len(set(self.media_ids))!=len(self.media_ids):raise ValueError('相册图片不能重复')
        if self.cover_id and self.cover_id not in self.media_ids:raise ValueError('封面必须是相册中的图片')
        return self

@admin.get('/{id}')
def read(id:UUID,db=Depends(db_dep)):
    a=db.get(Album,str(id))
    if not a:raise HTTPException(404,'相册不存在')
    return {'id':a.id,'name':a.name,'cover_id':a.cover_id,'expected_revision':a.revision,'media_ids':list(db.scalars(select(AlbumPhoto.media_id).where(AlbumPhoto.album_id==a.id).order_by(AlbumPhoto.position)))}

def save(db,d,a=None):
    write_lock(db)
    if (a.revision if a else 0)!=d.expected_revision:raise HTTPException(409,'相册已更新，请重新读取')
    ids=[str(x) for x in d.media_ids]
    if set(ids)!=set(db.scalars(select(MediaAsset.id).where(MediaAsset.id.in_(ids),MediaAsset.deleted_at.is_(None)))):raise HTTPException(422,'相册包含不存在的媒体')
    if not a:a=Album(id=str(uuid.uuid4()),revision=0);db.add(a)
    a.name=d.name.strip();a.cover_id=str(d.cover_id) if d.cover_id else None;a.revision+=1;db.flush()
    db.execute(delete(AlbumPhoto).where(AlbumPhoto.album_id==a.id))
    db.add_all(AlbumPhoto(album_id=a.id,media_id=mid,position=i) for i,mid in enumerate(ids));db.commit()
    return {'id':a.id,'revision':a.revision}

@admin.post('')
def create(d:AlbumIn,db=Depends(db_dep)):return save(db,d)
@admin.put('/{id}')
def update(id:UUID,d:AlbumIn,db=Depends(db_dep)):
    write_lock(db);a=db.get(Album,str(id))
    if not a:raise HTTPException(404,'相册不存在')
    return save(db,d,a)
@admin.delete('/{id}')
def remove(id:UUID,expected_revision:int=Query(ge=1),db=Depends(db_dep)):
    write_lock(db);a=db.get(Album,str(id))
    if not a:raise HTTPException(404,'相册不存在')
    if a.revision!=expected_revision:raise HTTPException(409,'相册已更新')
    db.execute(delete(AlbumPhoto).where(AlbumPhoto.album_id==a.id));db.delete(a);db.commit();return {'ok':True}

@router.get('/options')
def options(record_q:str=Query('',max_length=200),place_q:str=Query('',max_length=200),db=Depends(db_dep)):
    from ..services.blog import readable
    from ..content_models import ContentRecord
    from ..archive_models import Place,RecordPlace
    records=list(db.execute(readable().with_only_columns(ContentRecord.id,ContentRecord.title).where(ContentRecord.title.icontains(record_q,autoescape=True)).order_by(ContentRecord.display_date.desc(),ContentRecord.id).limit(50)))
    places=list(db.scalars(select(Place).where(Place.name.icontains(place_q,autoescape=True),Place.id.in_(select(RecordPlace.place_id).where(RecordPlace.record_id.in_(readable().with_only_columns(ContentRecord.id))))).order_by(Place.name,Place.id).limit(50)))
    return {'records':[{'id':rid,'name':title} for rid,title in records],'places':[{'id':p.id,'name':p.name,'city':p.city} for p in places]}
