from uuid import UUID
import uuid
from typing import Literal
from fastapi import APIRouter,Depends,Query,HTTPException
from sqlalchemy import select,func,or_,exists
from sqlalchemy.orm import aliased,defer
from pydantic import Field
from ..dependencies import db_dep,current_user,require_dynamic_blog
from ..content_models import ContentRecord,ContentType
from ..v5_models import FoodOccurrence,FoodContentType
from ..archive_models import RecordMedia,Place,MediaAsset
from ..life_models import ActivityMedia,TripActivity,TripPlan
from ..services.body_media import safe_excerpt
from ..content_schemas import StrictModel
from ..services.archive import write_lock
from ..services.food import sync
router=APIRouter(prefix='/api/food',dependencies=[Depends(current_user)])
admin=APIRouter(prefix='/api/admin/food',dependencies=[Depends(require_dynamic_blog)])
def query():
    return select(FoodOccurrence,ContentRecord).join(ContentRecord,FoodOccurrence.record_id==ContentRecord.id).join(ContentType,ContentType.id==ContentRecord.type_id).where(FoodOccurrence.active.is_(True),ContentRecord.deleted_at.is_(None),ContentRecord.status=='published',ContentType.active.is_(True)).options(defer(ContentRecord.body),defer(ContentRecord.values))
def food_context(db,rows):
    ids={r.id for f,r in rows};mark_ids={r.id for f,r in rows if f.source_kind in ('mark','article')}
    if not ids:return {},{},{},set(),{},set()
    covers={};marks={};activities={};bodies={}
    from ..services.record_mode import travel_expression
    trips=set(db.scalars(select(ContentRecord.id).where(ContentRecord.id.in_(ids),travel_expression(db))))
    article_ids={r.id for f,r in rows if f.source_kind=='article'}
    if article_ids:
        from sqlalchemy.orm.attributes import set_committed_value
        values=dict(db.execute(select(ContentRecord.id,ContentRecord.values).where(ContentRecord.id.in_(article_ids))).all())
        for f,r in rows:
            if r.id in values:set_committed_value(r,'values',values[r.id])
    for rid,mid in db.execute(select(RecordMedia.record_id,RecordMedia.media_id).join(MediaAsset,MediaAsset.id==RecordMedia.media_id).where(RecordMedia.record_id.in_(ids),MediaAsset.deleted_at.is_(None)).order_by(RecordMedia.cover.desc(),RecordMedia.position,RecordMedia.media_id)):covers.setdefault(rid,mid)
    # Reading body is restricted to records that need exact mark ownership; one batch.
    from types import SimpleNamespace
    from ..services.food import mark_media
    for rid,body,fmt,summary in db.execute(select(ContentRecord.id,ContentRecord.body,ContentRecord.body_format,ContentRecord.summary).where(ContentRecord.id.in_(mark_ids))):
        bodies[rid]=(body,fmt,summary)
        marks[rid]=mark_media(db,SimpleNamespace(id=rid,body=body,body_format=fmt)) if any(f.record_id==rid and f.source_kind=='mark' for f,r in rows) else {}
        if any(f.record_id==rid and f.source_kind=='article' for f,r in rows):
            from ..services.body_media import narrative_parser
            marks[rid]['__article__']=[token.meta['id'] for token in narrative_parser().parse(body) if token.type=='private_media'] if fmt==2 else []
    for aid,mid in db.execute(select(ActivityMedia.activity_id,ActivityMedia.media_id).join(TripActivity,TripActivity.id==ActivityMedia.activity_id).join(MediaAsset,MediaAsset.id==ActivityMedia.media_id).where(TripActivity.record_id.in_(ids),TripActivity.active.is_(True),ActivityMedia.active.is_(True),MediaAsset.deleted_at.is_(None)).order_by(ActivityMedia.media_id)):activities.setdefault(aid,mid)
    active=set(db.scalars(select(MediaAsset.id).where(MediaAsset.id.in_({m for x in marks.values() for mids in x.values() for m in mids}),MediaAsset.deleted_at.is_(None))))
    return covers,marks,activities,active,bodies,trips

def item(db,f,r,places=None,context=None):
    place=(places.get(f.place_id) if places is not None else db.get(Place,f.place_id)) if f.place_id else None
    covers,marks,activities,active,bodies,trips=context or food_context(db,[(f,r)])
    if f.source_kind=='article':cover=covers.get(r.id)
    elif f.source_kind=='activity':cover=activities.get(f.source_key.removeprefix('activity:'))
    else:cover=next((id for id in marks.get(r.id,{}).get(f.source_key,[]) if id in active),None)
    info={}
    if f.source_kind=='article':
        from ..services.food import article_info
        info=article_info(db,r)
        if not cover:cover=next((mid for mid in marks.get(r.id,{}).get('__article__',[]) if mid in active),None)
    body,fmt,summary=bodies.get(r.id,('',2,''))
    description=safe_excerpt(info.get('food_review') or summary or body,fmt,300) if f.source_kind=='article' else safe_excerpt(f.description,2,300)
    day=info.get('food_date') if f.source_kind=='article' else f.day.isoformat() if f.day else None
    shop=info.get('food_shop') or (f.name if f.source_kind!='article' else '')
    return {'article_date':r.display_date.isoformat(),'id':f.id,'record_id':r.id,'record_revision':r.revision,'title':r.title,'name':f.name,'shop_name':shop,'address':info.get('food_address') or (place.address if place else ''),'description':description,'day':day,'city':f.city_override if f.city_override is not None else f.city,'city_source':'manual' if f.city_override is not None else f.city_source,'category':f.category,'place':{'id':place.id,'name':place.name,'city':place.city,'address':place.address} if place else None,'source_kind':f.source_kind,'image_source':('nested-mark' if f.source_kind=='mark' else f.source_kind) if cover else 'none','travel_source':r.title if r.id in trips else None,'cover_id':cover,'revision':f.revision}
@router.get('')
def listing(q:str=Query('',max_length=200),city:str=Query('',max_length=100),category:str=Query('',max_length=100),place_id:UUID|None=None,year:int|None=Query(None,ge=1,le=9999),kind:Literal['visits','articles']='visits',sort:Literal['newest','oldest','name']='newest',page:int=Query(1,ge=1,le=1000000),page_size:int=Query(20,ge=1,le=50),db=Depends(db_dep)):
    stmt=query()
    if kind=='articles':stmt=stmt.where(FoodOccurrence.source_kind=='article')
    else:
        other=aliased(FoodOccurrence)
        stmt=stmt.where(or_(FoodOccurrence.source_kind!='article',~exists(select(other.id).where(other.record_id==FoodOccurrence.record_id,other.active.is_(True),other.source_kind!='article'))))
    if q:stmt=stmt.where(or_(FoodOccurrence.name.icontains(q,autoescape=True),FoodOccurrence.description.icontains(q,autoescape=True),ContentRecord.title.icontains(q,autoescape=True)))
    if city:stmt=stmt.where(func.coalesce(FoodOccurrence.city_override,FoodOccurrence.city)==('' if city=='待分类' else city))
    if category:stmt=stmt.where(FoodOccurrence.category==category)
    if place_id:stmt=stmt.where(FoodOccurrence.place_id==str(place_id))
    if year:stmt=stmt.where(func.extract('year',func.coalesce(FoodOccurrence.day,ContentRecord.display_date))==year)
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    order=[FoodOccurrence.name,FoodOccurrence.id] if sort=='name' else [func.coalesce(FoodOccurrence.day,ContentRecord.display_date).asc() if sort=='oldest' else func.coalesce(FoodOccurrence.day,ContentRecord.display_date).desc(),FoodOccurrence.id]
    rows=db.execute(stmt.order_by(*order).offset((page-1)*page_size).limit(page_size)).all()
    ids=[r.id for f,r in rows];pids={f.place_id for f,r in rows if f.place_id}
    places={p.id:p for p in db.scalars(select(Place).where(Place.id.in_(pids)))} if pids else {}
    context=food_context(db,rows)
    return {'items':[item(db,f,r,places,context) for f,r in rows],'total':total,'page':page,'page_size':page_size,'note':'文章与出现记录分开；餐厅图片只使用明确关联，无图不继承旅行封面'}
@router.get('/{id}')
def detail(id:UUID,db=Depends(db_dep)):
    row=db.execute(query().where(FoodOccurrence.id==str(id))).first()
    if not row:raise HTTPException(404,'美食记录不存在或尚未发布')
    return item(db,*row)
class Patch(StrictModel):
    expected_revision:int=Field(ge=1)
    city_override:str|None=Field(None,max_length=100)
    category:str=Field('',max_length=100)
@admin.put('/occurrences/{id}')
def edit(id:UUID,d:Patch,db=Depends(db_dep)):
    write_lock(db);f=db.get(FoodOccurrence,str(id))
    if not f:raise HTTPException(404,'美食记录不存在')
    if f.revision!=d.expected_revision:raise HTTPException(409,'美食索引已更新，请重新读取')
    f.city_override=d.city_override;f.category=d.category;f.revision+=1;db.commit();return {'ok':True,'revision':f.revision}
@admin.post('/rebuild')
def rebuild(after:UUID|None=None,db=Depends(db_dep)):
    write_lock(db);stmt=select(ContentRecord).order_by(ContentRecord.id).limit(50)
    if after:stmt=stmt.where(ContentRecord.id>str(after))
    rows=list(db.scalars(stmt))
    for r in rows:sync(db,r)
    db.commit();return {'count':len(rows),'next':rows[-1].id if len(rows)==50 else None,'source_records_changed':False}
@admin.post('/install-template')
def install(db=Depends(db_dep),u=Depends(require_dynamic_blog)):
    write_lock(db);existing=db.scalar(select(FoodContentType).join(ContentType,ContentType.id==FoodContentType.type_id).where(ContentType.active.is_(True)).order_by(FoodContentType.type_id).limit(1))
    from ..services.templates import save_template,template_data,get_template
    if existing:return template_data(db,get_template(db,existing.template_id))
    from ..template_schemas import TemplateIn
    fields=food_fields()
    data=TemplateIn(slug='food-'+uuid.uuid4().hex[:8],name='美食记录',description='餐厅、独立美食或家庭制作；不强制绑定餐厅',fields=fields,modules=[{'id':str(uuid.uuid4()),'kind':k,'enabled':True,'field_ids':[f['key'] for f in fields] if k=='fields' else []} for k in ['header','fields','body','gallery','related']])
    t=save_template(db,data,u.id);db.add(FoodContentType(type_id=t.type_id,template_id=t.id));db.commit();return template_data(db,t)


FOOD_FIELDS=[('food_shop','餐厅 / 店铺名称','short_text'),('food_date','实际用餐日期','date'),('food_city','城市','short_text'),('food_address','具体地点 / 地址','short_text'),('food_review','美食描述与评价','long_text')]
def food_fields():
    return [{'key':str(uuid.uuid4()),'group':'餐厅信息','field':{'purpose':purpose,'name':name,'kind':kind,'position':i,'required':False}} for i,(purpose,name,kind) in enumerate(FOOD_FIELDS)]

class FoodFieldsIn(StrictModel):
    expected_type_revision:int=Field(ge=1)
    expected_template_revision:int=Field(ge=1)
    confirmation:Literal['新增可选餐厅信息字段']

@admin.post('/types/{type_id}/fields')
def add_food_fields(type_id:UUID,d:FoodFieldsIn,db=Depends(db_dep),u=Depends(require_dynamic_blog)):
    write_lock(db);binding=db.get(FoodContentType,str(type_id))
    if not binding:raise HTTPException(404,'不是美食模板类型')
    from ..services.templates import get_template,template_data,save_template
    from ..template_schemas import TemplateUpdate
    from ..services.content import type_data,get_type
    t=get_template(db,binding.template_id);ct=get_type(db,str(type_id),lock=True)
    if (ct.revision,t.revision)!=(d.expected_type_revision,d.expected_template_revision):raise HTTPException(409,'模板或字段配置已更新，请重新读取')
    current=template_data(db,t);configured={f['field'].get('purpose') for f in current['fields']}
    additions=[f for f in food_fields() if f['field']['purpose'] not in configured]
    if len(current['fields'])+len(additions)>50:raise HTTPException(409,'字段数量达到上限，请先审核模板中可复用字段；未修改历史记录')
    if additions:
        spec=TemplateUpdate(slug=t.slug,name=t.name,description=t.description,active=t.active,expected_revision=t.revision,expected_type_revision=ct.revision,fields=current['fields']+additions,modules=current['modules'])
        save_template(db,spec,u.id,t)
    db.commit()
    return {'template':template_data(db,t),'type':type_data(db,ct),'records_changed':False}
