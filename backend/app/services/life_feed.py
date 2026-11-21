"""Read-only aggregation from existing published records, never annual copies."""
from datetime import date
from sqlalchemy import select,func,extract
from ..content_models import ContentRecord,ContentType
from ..archive_models import RecordMedia,MediaAsset,RecordLink
from .blog import readable,page_records,summary,available,summaries

def year_query(year=None,type_id=None):
    q=readable()
    if year:q=q.where(ContentRecord.display_date>=date(year,1,1),ContentRecord.display_date<=date(year,12,31))
    if type_id:q=q.where(ContentRecord.type_id==str(type_id))
    return q

def filters(db):
    sub=readable().with_only_columns(ContentRecord.id,ContentRecord.type_id,ContentRecord.display_date).subquery()
    years=[int(x) for x in db.scalars(select(extract('year',sub.c.display_date)).distinct().order_by(extract('year',sub.c.display_date).desc()))]
    types=[{'id':id,'name':name} for id,name in db.execute(select(ContentType.id,ContentType.name).where(ContentType.id.in_(select(sub.c.type_id))).order_by(ContentType.name,ContentType.id))]
    return {'years':years,'types':types}

def feed(db,year=None,type_id=None,page=1):
    return {**page_records(db,year_query(year,type_id),page,20),**filters(db)}

def review(db,year,type_id=None,page=1):
    query=year_query(year,type_id);sub=query.with_only_columns(ContentRecord.id,ContentRecord.type_id).subquery()
    counts=[{'type_id':id,'name':name,'count':count} for id,name,count in db.execute(select(ContentType.id,ContentType.name,func.count()).join(sub,sub.c.type_id==ContentType.id).group_by(ContentType.id,ContentType.name).order_by(ContentType.name))]
    # Bounded selection, stable and private. Cover first, then record date/photo order.
    rows=db.execute(select(RecordMedia.record_id,RecordMedia.caption,MediaAsset.id,MediaAsset.alt,MediaAsset.title,ContentRecord.title.label("record_title")).join(MediaAsset,RecordMedia.media_id==MediaAsset.id).join(ContentRecord,RecordMedia.record_id==ContentRecord.id).where(ContentRecord.id.in_(select(sub.c.id)),MediaAsset.deleted_at.is_(None)).order_by(RecordMedia.cover.desc(),ContentRecord.display_date.desc(),ContentRecord.id,RecordMedia.position).limit(200))
    photos={}
    for row in rows:
        if row.id not in photos and len(photos)>=24:continue
        p=photos.setdefault(row.id,{'id':row.id,'alt':row.alt,'caption':row.caption or row.title,'records':[]})
        if not any(x['id']==row.record_id for x in p['records']):p['records'].append({'id':row.record_id,'title':row.record_title})
    edges=list(db.execute(select(RecordLink.target_id,RecordLink.label).where(RecordLink.source_id.in_(select(sub.c.id))).distinct().order_by(RecordLink.target_id,RecordLink.label).limit(100)))
    related_data={r['id']:r for r in summaries(db,readable().where(ContentRecord.id.in_([id for id,label in edges])))} if edges else {}
    related=[{**related_data[id],'label':label} for id,label in edges if id in related_data]
    return {**feed(db,year,type_id,page),'year':year,'counts':counts,'photos':list(photos.values()),'related':related}
