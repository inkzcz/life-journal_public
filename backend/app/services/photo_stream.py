"""Permission filtering precedes aggregation. No EXIF/upload-time guesses."""
from sqlalchemy import select,union,func,case,and_,or_,exists,cast,String
from ..archive_models import RecordMedia,MediaAsset,RecordMarkedPlace
from ..content_models import ContentRecord,RecordBodyMedia
from ..life_models import PhotoAnnotation,TripActivity,ActivityMedia
from ..experience_models import ArticleOptions,Experience,ExperienceMedia
from ..album_models import AlbumPhoto
from .blog import readable

def references():
    return union(select(RecordMedia.record_id,RecordMedia.media_id),select(RecordBodyMedia.record_id,RecordBodyMedia.media_id),
        select(TripActivity.record_id,ActivityMedia.media_id).join(ActivityMedia,ActivityMedia.activity_id==TripActivity.id).where(TripActivity.active.is_(True),ActivityMedia.active.is_(True))).subquery('photo_refs')

def visible_refs():
    refs=references()
    day=func.coalesce(PhotoAnnotation.taken_on,MediaAsset.captured_on,case((or_(ArticleOptions.end_date.is_(None),ArticleOptions.end_date==ContentRecord.display_date),ContentRecord.display_date),else_=None))
    return select(refs.c.record_id,refs.c.media_id,day.label('day'),PhotoAnnotation.place_id).join(ContentRecord,ContentRecord.id==refs.c.record_id).join(MediaAsset,MediaAsset.id==refs.c.media_id).outerjoin(ArticleOptions,ArticleOptions.record_id==ContentRecord.id).outerjoin(PhotoAnnotation,and_(PhotoAnnotation.record_id==ContentRecord.id,PhotoAnnotation.media_id==MediaAsset.id,PhotoAnnotation.active.is_(True))).where(ContentRecord.id.in_(readable().with_only_columns(ContentRecord.id)),MediaAsset.deleted_at.is_(None))

def stream(db,*,page=1,year=None,month=None,record_id=None,place_id=None,kind=None,album_id=None):
    refs=visible_refs().subquery();q=select(refs.c.media_id,func.max(refs.c.day).label('day')).group_by(refs.c.media_id)
    if year:q=q.where(func.extract('year',refs.c.day)==year)
    if month:q=q.where(func.extract('month',refs.c.day)==month)
    if record_id:q=q.where(refs.c.record_id==str(record_id))
    if place_id:
        via_entry=exists(select(ExperienceMedia.media_id).join(Experience,and_(Experience.record_id==ExperienceMedia.record_id,Experience.id==ExperienceMedia.entry_id)).join(RecordMarkedPlace,and_(RecordMarkedPlace.record_id==Experience.record_id,func.replace(RecordMarkedPlace.source_key,'-','')=='entry:'+func.replace(cast(Experience.id,String),'-',''))).where(ExperienceMedia.record_id==refs.c.record_id,ExperienceMedia.media_id==refs.c.media_id,ExperienceMedia.active.is_(True),Experience.active.is_(True),RecordMarkedPlace.place_id==str(place_id)))
        via_activity=exists(select(ActivityMedia.media_id).join(TripActivity,TripActivity.id==ActivityMedia.activity_id).where(ActivityMedia.media_id==refs.c.media_id,TripActivity.record_id==refs.c.record_id,ActivityMedia.active.is_(True),TripActivity.active.is_(True),TripActivity.place_id==str(place_id)))
        from ..v5_models import FoodOccurrence
        from .food import mark_media
        legacy=set()
        for r in db.scalars(readable().where(ContentRecord.id.in_(select(FoodOccurrence.record_id).where(FoodOccurrence.active.is_(True),FoodOccurrence.place_id==str(place_id)))).execution_options(yield_per=100)):
            keys=set(db.scalars(select(FoodOccurrence.source_key).where(FoodOccurrence.record_id==r.id,FoodOccurrence.place_id==str(place_id),FoodOccurrence.active.is_(True))))
            legacy.update(mid for key,ids in mark_media(db,r).items() if key in keys for mid in ids)
        q=q.where(or_(refs.c.place_id==str(place_id),via_entry,via_activity,refs.c.media_id.in_(legacy)))
    if kind:
        em=select(ExperienceMedia.media_id).join(Experience,and_(Experience.record_id==ExperienceMedia.record_id,Experience.id==ExperienceMedia.entry_id)).where(ExperienceMedia.record_id==refs.c.record_id,ExperienceMedia.active.is_(True),Experience.active.is_(True),Experience.kind==kind)
        if kind=='f':
            # Historical @f associations, still requiring explicit list ownership.
            from ..content_models import ContentRecord as R
            from .food import mark_media
            historical=set()
            for r in db.scalars(readable().where(ContentRecord.body.contains('@f')).execution_options(yield_per=100)):
                historical.update(mid for ids in mark_media(db,r).values() for mid in ids)
            q=q.where(or_(refs.c.media_id.in_(em),refs.c.media_id.in_(historical)))
        else:q=q.where(refs.c.media_id.in_(em))
    if album_id:q=q.where(refs.c.media_id.in_(select(AlbumPhoto.media_id).where(AlbumPhoto.album_id==str(album_id))))
    total=db.scalar(select(func.count()).select_from(q.subquery()))
    ordered=q.order_by(func.max(refs.c.day).desc().nullslast(),refs.c.media_id)
    if album_id:
        pos=select(AlbumPhoto.position).where(AlbumPhoto.album_id==str(album_id),AlbumPhoto.media_id==refs.c.media_id).correlate(refs).scalar_subquery()
        ordered=q.order_by(pos,refs.c.media_id)
    rows=list(db.execute(ordered.offset((page-1)*24).limit(24)))
    ids=[r.media_id for r in rows];assets={a.id:a for a in db.scalars(select(MediaAsset).where(MediaAsset.id.in_(ids)))}
    sources={mid:[] for mid in ids}
    for rid,mid,day,pid,title,start,end,taken,captured in db.execute(select(refs.c.record_id,refs.c.media_id,refs.c.day,refs.c.place_id,ContentRecord.title,ContentRecord.display_date,ArticleOptions.end_date,PhotoAnnotation.taken_on,MediaAsset.captured_on).join(ContentRecord,ContentRecord.id==refs.c.record_id).join(MediaAsset,MediaAsset.id==refs.c.media_id).outerjoin(ArticleOptions,ArticleOptions.record_id==ContentRecord.id).outerjoin(PhotoAnnotation,and_(PhotoAnnotation.record_id==ContentRecord.id,PhotoAnnotation.media_id==MediaAsset.id,PhotoAnnotation.active.is_(True))).where(refs.c.media_id.in_(ids)).order_by(ContentRecord.display_date.desc(),ContentRecord.id)):
        sources[mid].append({'id':rid,'title':title,'date':day.isoformat() if day else None,'date_source':'annotation' if taken else 'capture' if captured else 'article-single-date' if not end or end==start else 'article-range-unknown','range_start':start.isoformat(),'range_end':end.isoformat() if end else None,'place_id':pid})
    return {'items':[{'id':r.media_id,'alt':assets[r.media_id].alt,'title':assets[r.media_id].title,'caption':assets[r.media_id].title,'date':r.day.isoformat() if r.day else None,'records':sources[r.media_id]} for r in rows], 'total':total,'page':page,'page_size':24}
