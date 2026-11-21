import uuid
from fastapi import HTTPException,Depends
from sqlalchemy import select,func,or_,and_,case
from ..dependencies import current_user,get_settings
from ..blog_models import Section,SectionType,SiteConfig,NavigationItem
from ..content_models import ContentRecord,ContentType
from ..archive_models import MediaAsset,RecordMedia,RecordLink,Place,RecordPlace
from .content import fields_for
from .body_media import safe_excerpt

DEFAULT_LAYOUT={'title':'Life Journal','description':'收藏日常，留住时光。','modules':[{'id':'00000000-0000-4000-8000-000000000001','kind':'hero','enabled':True,'title':'生活值得慢慢收藏','text':'在这里，安放故事与值得记住的片刻。','count':6,'layout':'feature','section_id':None,'type_id':None,'record_ids':[]},{'id':'00000000-0000-4000-8000-000000000002','kind':'latest','enabled':True,'title':'最近的故事','text':'','count':6,'layout':'grid2','section_id':None,'type_id':None,'record_ids':[]}]}

def reader(user=Depends(current_user),settings=Depends(get_settings)):
    return user

def config_data(db,key):
    row=db.scalar(select(SiteConfig).where(SiteConfig.key==key))
    default={'appearance':{'theme':'modern','mode':'system'},'layout':DEFAULT_LAYOUT,'navigation':{}}[key]
    return {**(row.value if row else default),'revision':row.revision if row else 0}

def save_config(db,key,value,expected):
    row=db.scalar(select(SiteConfig).where(SiteConfig.key==key))
    if (row.revision if row else 0)!=expected:raise HTTPException(409,'配置已更新，请重新读取；未保存输入会保留')
    if row:row.value=value;row.revision+=1
    else:db.add(SiteConfig(id=str(uuid.uuid4()),key=key,value=value,revision=1))
    db.flush()

def readable():
    return select(ContentRecord).join(ContentType,ContentRecord.type_id==ContentType.id).where(ContentRecord.status=='published',ContentRecord.deleted_at.is_(None),ContentType.active.is_(True))

def available(db,id):return db.scalar(readable().where(ContentRecord.id==str(id)))

def sections_data(db,rows):
    rows=list(rows);groups={s.id:[] for s in rows}
    if groups:
        for sid,tid in db.execute(select(SectionType.section_id,SectionType.type_id).where(SectionType.section_id.in_(groups))):groups[sid].append(tid)
    return [{k:getattr(s,k) for k in ['id','name','slug','description','cover_id','position','active','layout','revision']}|{'type_ids':groups[s.id]} for s in rows]

def section_data(db,s):return sections_data(db,[s])[0]

def section_query(query,id):
    return query.where(ContentRecord.type_id.in_(select(SectionType.type_id).where(SectionType.section_id==id)))

def record_order():return (ContentRecord.display_date.desc(),ContentRecord.id.asc())

def summaries(db,query):
    """Paged scalar projection plus one cover batch; no JSONB/ORM hydration. Clean before truncating so media metadata cannot consume the readable budget."""
    source=func.coalesce(func.nullif(ContentRecord.summary,''),ContentRecord.body)
    # Plain lists remain a bounded projection. Opaque image blocks must be
    # removed before truncation, even when several long blocks lead the story.
    excerpt=case((or_(source.contains(':::lj-media-v'),source.contains(':::lj-entry-v')),source),else_=func.substr(source,1,4096))
    rows=db.execute(query.with_only_columns(ContentRecord.id,ContentRecord.title,ContentRecord.display_date,
        ContentType.name.label('type_name'),ContentRecord.body_format,excerpt.label('excerpt'))).all()
    ids=[r.id for r in rows]
    covers=select(RecordMedia.record_id,MediaAsset.id.label('media_id'),MediaAsset.alt,MediaAsset.preview_width,MediaAsset.preview_height,RecordMedia.caption,
        func.row_number().over(partition_by=RecordMedia.record_id,order_by=(RecordMedia.cover.desc(),RecordMedia.position,MediaAsset.id)).label('rank')).join(MediaAsset,RecordMedia.media_id==MediaAsset.id).where(RecordMedia.record_id.in_(ids),MediaAsset.deleted_at.is_(None)).subquery()
    images={r.record_id:{'id':r.media_id,'alt':r.alt,'caption':r.caption,'width':r.preview_width,'height':r.preview_height} for r in db.execute(select(covers).where(covers.c.rank==1))} if ids else {}
    return [{'id':r.id,'title':r.title,'display_date':r.display_date.isoformat(),'type_name':r.type_name,'excerpt':safe_excerpt(r.excerpt,r.body_format),'cover':images.get(r.id)} for r in rows]

def summary(db,r):
    # Current Admin preview may be a draft; callers control its authorization.
    return summaries(db,select(ContentRecord).join(ContentType,ContentRecord.type_id==ContentType.id).where(ContentRecord.id==r.id))[0]

def page_records(db,query,page=1,size=12):
    count=db.scalar(select(func.count()).select_from(query.with_only_columns(ContentRecord.id).subquery()))
    return {'items':summaries(db,query.order_by(*record_order()).offset((page-1)*size).limit(size)),'total':count,'page':page,'page_size':size}

def detail(db,r):
    from .templates import binding_data
    from .life import life_data
    binding=binding_data(db,r)
    template={'version':binding['version'],'config':{'modules':binding['config']['modules']}} if binding else None
    definitions=fields_for(db,r.type_id,r.schema_version)
    fields=[]
    for f in definitions:
        value=r.values.get(f['id']);chosen=value if isinstance(value,list) else [value]
        fields.append({k:f[k] for k in ['id','kind','name','description','position']}|{'rules':{'options':[o for o in f['rules'].get('options',[]) if o['id'] in chosen]}})
    # Explicit reader DTO; never expose Admin snapshots, uploader or original paths.
    media=[{'id':m.id,'alt':m.alt,'title':m.title,'caption':ref.caption,'cover':ref.cover,'width':m.preview_width,'height':m.preview_height} for ref,m in db.execute(select(RecordMedia,MediaAsset).join(MediaAsset,RecordMedia.media_id==MediaAsset.id).where(RecordMedia.record_id==r.id,MediaAsset.deleted_at.is_(None)).order_by(RecordMedia.position))]
    targets=list(db.execute(select(RecordLink.target_id,RecordLink.label).where(RecordLink.source_id==r.id)))
    related={x['id']:x for x in summaries(db,readable().where(ContentRecord.id.in_([id for id,label in targets])))} if targets else {}
    links=[{**related[id],'label':label} for id,label in targets if id in related]
    places=[{k:getattr(p,k) for k in ['id','name','country','region','city','address','category','notes']}|{'latitude':str(p.latitude) if p.latitude is not None else None,'longitude':str(p.longitude) if p.longitude is not None else None} for p in db.scalars(select(Place).join(RecordPlace,RecordPlace.place_id==Place.id).where(RecordPlace.record_id==r.id))]
    sections=list(db.scalars(select(Section).join(SectionType,SectionType.section_id==Section.id).where(SectionType.type_id==r.type_id,Section.active.is_(True)).order_by(Section.position)))
    from .tags import record_tags
    from .experiences import options
    from ..experience_models import Experience
    experiences=[{'id':e.id,'name':e.name,'kind':e.kind,'active':e.active,'fields':e.fields} for e in db.scalars(select(Experience).where(Experience.record_id==r.id))]
    return {**summary(db,r),'article':options(db,r),'experiences':experiences,'tags':record_tags(db,[r.id]).get(r.id,[]),'life':life_data(db,r.id),'template':template,'body':r.body,'body_format':r.body_format,'schema_version':r.schema_version,'fields':fields,'values':{f['id']:r.values[f['id']] for f in fields if f['id'] in r.values},'media':media,'links':links,'places':places,'sections':sections_data(db,sections)}

def navigation(db,private=True):
    rows=list(db.scalars(select(NavigationItem).order_by(NavigationItem.position)))
    record_ids={n.record_id for n in rows if n.kind=='record'}
    section_ids={n.section_id for n in rows if n.kind=='section'}
    visible=set(db.scalars(readable().with_only_columns(ContentRecord.id).where(ContentRecord.id.in_(record_ids)))) if private and record_ids else set()
    active=set(db.scalars(select(Section.id).where(Section.id.in_(section_ids),Section.active.is_(True)))) if private and section_ids else set()
    result=[]
    for n in rows:
        if private and (not n.active or n.kind=='record' and n.record_id not in visible or n.kind=='section' and n.section_id not in active):continue
        result.append({k:getattr(n,k) for k in ['id','parent_id','name','kind','section_id','record_id','page','active']})
    if private:
        roots={n['id'] for n in result if not n['parent_id']}
        result=[n for n in result if not n['parent_id'] or n['parent_id'] in roots]
    return result

def home(db):
    layout=config_data(db,'layout');modules=[]
    for m in layout['modules']:
        if not m['enabled']:continue
        if m['kind']=='anniversary_calendar':
            from ..calendar.service import today,list_events
            from datetime import timedelta
            start=today(db)
            modules.append({**{k:v for k,v in m.items() if k not in {'record_ids','type_id','section_id'}},'items':[],'events':list_events(db,start,start+timedelta(days=m.get('horizon',30)),m['count'])})
            continue
        query=readable()
        if m.get('type_id'):query=query.where(ContentRecord.type_id==m['type_id'])
        if m.get('section_id'):
            s=db.get(Section,m['section_id'])
            if not s or not s.active:continue
            query=section_query(query,s.id)
        if m['kind'] in {'featured','gallery'} and m.get('record_ids'):query=query.where(ContentRecord.id.in_(m['record_ids']))
        elif m['kind']=='featured':query=query.where(ContentRecord.id.is_(None))
        data=page_records(db,query,size=m['count']) if m['kind'] not in {'hero','text'} else {'items':[]}
        if m['kind']=='gallery':data['items']=[x for x in data['items'] if x['cover']]
        modules.append({**{k:v for k,v in m.items() if k not in {'record_ids','type_id','section_id'}},'items':data['items']})
    return {'title':layout['title'],'description':layout['description'],'modules':modules}


def adjacent_records(db,r):
    # Same total order as page_records; keyset lookups work across page boundaries.
    previous=db.scalar(readable().with_only_columns(ContentRecord.id).where(ContentRecord.id!=r.id,or_(ContentRecord.display_date>r.display_date,and_(ContentRecord.display_date==r.display_date,ContentRecord.id<r.id))).order_by(ContentRecord.display_date.asc(),ContentRecord.id.desc()).limit(1))
    following=db.scalar(readable().with_only_columns(ContentRecord.id).where(ContentRecord.id!=r.id,or_(ContentRecord.display_date<r.display_date,and_(ContentRecord.display_date==r.display_date,ContentRecord.id>r.id))).order_by(*record_order()).limit(1))
    ids=[id for id in [previous,following] if id]
    if not ids:return {'context':'global','previous':None,'next':None}
    # Batch minimal reader DTOs. Do not call detail/summary or load bodies/history.
    covers=select(RecordMedia.record_id,MediaAsset.id.label('media_id'),MediaAsset.alt,func.row_number().over(partition_by=RecordMedia.record_id,order_by=(RecordMedia.cover.desc(),RecordMedia.position,MediaAsset.id)).label('rank')).join(MediaAsset,RecordMedia.media_id==MediaAsset.id).where(RecordMedia.record_id.in_(ids),MediaAsset.deleted_at.is_(None)).subquery()
    rows=db.execute(select(ContentRecord.id,ContentRecord.title,ContentRecord.display_date,covers.c.media_id,covers.c.alt).join(ContentType,ContentRecord.type_id==ContentType.id).outerjoin(covers,and_(covers.c.record_id==ContentRecord.id,covers.c.rank==1)).where(ContentRecord.id.in_(ids),ContentRecord.status=='published',ContentRecord.deleted_at.is_(None),ContentType.active.is_(True)))
    data={row.id:{'id':row.id,'title':row.title,'display_date':row.display_date.isoformat(),'cover':{'id':row.media_id,'alt':row.alt} if row.media_id else None} for row in rows}
    return {'context':'global','previous':data.get(previous) if previous else None,'next':data.get(following) if following else None}
