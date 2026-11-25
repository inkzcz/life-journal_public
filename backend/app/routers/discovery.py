"""Private, bounded archive queries. No bodies/JSONB are materialized for result pages."""
from ..services.body_media import safe_excerpt
from datetime import date
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,Query
from sqlalchemy import select,func,or_,and_,extract,text,String
from sqlalchemy.orm import Session
from ..dependencies import db_dep
from ..services.blog import reader,readable,record_order
from ..content_models import ContentRecord as R,ContentType as T,VersionField,FieldDefinition
from ..tag_models import Tag,RecordTag
from ..archive_models import RecordMedia,MediaAsset
from ..services.tags import record_tags
router=APIRouter(prefix='/api/blog/archive',dependencies=[Depends(reader)])

@router.get('')
def archive(q:str=Query('',max_length=200),year:int|None=Query(None,ge=1,le=9999),
            type:UUID|None=None,record_mode:Literal['daily','travel']|None=None,tag:list[UUID]=Query(default=[],max_length=10),
            page:int=Query(1,ge=1,le=100000),page_size:int=Query(20,ge=1,le=50),db:Session=Depends(db_dep)):
    if db.bind.dialect.name=='postgresql':db.execute(text("SET LOCAL statement_timeout = '5s'"))
    base=readable().with_only_columns(R.id,R.title,R.display_date,T.name.label('type_name'),T.id.label('type_id'),R.body_format,func.substr(R.body,1,220).label('excerpt'))
    if record_mode:
        from ..services.record_mode import travel_expression
        base=base.where(travel_expression(db).is_(record_mode=='travel'))
    if year:base=base.where(R.display_date>=date(year,1,1),R.display_date<=date(year,12,31))
    if type:base=base.where(R.type_id==str(type))
    for id in set(map(str,tag)):
        base=base.where(select(RecordTag.record_id).where(RecordTag.record_id==R.id,RecordTag.tag_id==id).exists())
    if q.strip():
        keyword=q.strip()
        tags=select(RecordTag.record_id).join(Tag,RecordTag.tag_id==Tag.id).where(RecordTag.record_id==R.id,Tag.name.icontains(keyword,autoescape=True)).exists()
        # Only opted-in active textual fields in this record's immutable schema.
        fields=select(VersionField.field_id).join(FieldDefinition,VersionField.field_id==FieldDefinition.id).where(VersionField.type_id==R.type_id,VersionField.version==R.schema_version,VersionField.active.is_(True),VersionField.rules['searchable'].as_boolean().is_(True),FieldDefinition.kind.in_(['short_text','long_text','markdown']))
        if db.bind.dialect.name=='postgresql':
            value=func.jsonb_extract_path_text(R.values,func.cast(VersionField.field_id,String))
        else:
            # SQLAlchemy stores SQLite UUID columns as hex, while JSON object
            # keys retain the canonical hyphenated UUID supplied by the API.
            key=func.cast(VersionField.field_id,String)
            key=func.substr(key,1,8)+'-'+func.substr(key,9,4)+'-'+func.substr(key,13,4)+'-'+func.substr(key,17,4)+'-'+func.substr(key,21,12)
            value=func.json_extract(R.values,'$."'+key+'"')
        fields=fields.where(value.icontains(keyword,autoescape=True)).exists()
        base=base.where(or_(R.title.icontains(keyword,autoescape=True),R.body.icontains(keyword,autoescape=True),T.name.icontains(keyword,autoescape=True),tags,fields))
    from ..services.record_mode import travel_expression
    base=base.add_columns(travel_expression(db).label('travel_enabled'))
    total=db.scalar(select(func.count()).select_from(base.subquery()))
    rows=db.execute(base.order_by(*record_order()).offset((page-1)*page_size).limit(page_size)).all()
    ids=[r.id for r in rows];labels=record_tags(db,ids)
    covers=select(RecordMedia.record_id,MediaAsset.id,MediaAsset.alt,func.row_number().over(partition_by=RecordMedia.record_id,order_by=(RecordMedia.cover.desc(),RecordMedia.position,MediaAsset.id)).label('rank')).join(MediaAsset,RecordMedia.media_id==MediaAsset.id).where(RecordMedia.record_id.in_(ids),MediaAsset.deleted_at.is_(None)).subquery()
    images={r.record_id:{'id':r.id,'alt':r.alt} for r in db.execute(select(covers).where(covers.c.rank==1))} if ids else {}
    return {'items':[{'id':r.id,'source':'dynamic','title':r.title,'display_date':r.display_date.isoformat(),'type_id':r.type_id,'type_name':r.type_name,'travel_enabled':r.travel_enabled,'record_mode_name':'旅行记录' if r.travel_enabled else '日常记录','excerpt':safe_excerpt(r.excerpt,r.body_format),'tags':labels.get(r.id,[]),'cover':images.get(r.id)} for r in rows],'total':total,'page':page,'page_size':page_size}

@router.get('/facets')
def facets(db:Session=Depends(db_dep)):
    visible=readable().with_only_columns(R.id,R.type_id,R.display_date).subquery()
    years=[{'year':int(y),'count':n} for y,n in db.execute(select(extract('year',visible.c.display_date),func.count()).group_by(extract('year',visible.c.display_date)).order_by(extract('year',visible.c.display_date).desc()))]
    types=[{'id':id,'name':name,'count':n} for id,name,n in db.execute(select(T.id,T.name,func.count()).join(visible,visible.c.type_id==T.id).group_by(T.id,T.name).order_by(T.name,T.id))]
    tags=[{'id':id,'name':name,'count':n} for id,name,n in db.execute(select(Tag.id,Tag.name,func.count()).join(RecordTag,RecordTag.tag_id==Tag.id).join(visible,visible.c.id==RecordTag.record_id).group_by(Tag.id,Tag.name).order_by(Tag.normalized_name,Tag.id).limit(1000))]
    return {'years':years,'types':types,'tags':tags,'counts_scope':'all_visible_published','tags_truncated':len(tags)==1000}
