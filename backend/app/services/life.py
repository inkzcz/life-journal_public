"""Called inside the record's existing lock, optimistic update and revision transaction."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import undefer_group
from ..life_models import TripPlan,TripActivity,ActivityMedia,PhotoAnnotation
from ..archive_models import RecordMedia,RecordPlace,MediaAsset
from ..life_schemas import LifeIn


def life_data(db,id):
    plan=db.get(TripPlan,id)
    from ..experience_models import ActivityExperience,Experience
    activities=[]
    for a in db.scalars(select(TripActivity).options(undefer_group('activity_details')).where(TripActivity.record_id==id,TripActivity.active.is_(True)).order_by(TripActivity.position,TripActivity.id)):
        link=db.get(ActivityExperience,a.id)
        activities.append({'experience_id':link.entry_id if link else None,'id':a.id,'day':a.day.isoformat(),'time':a.time,'title':a.title,'description':a.description,'place_id':a.place_id,
                           **{k:getattr(a,k) for k in ['kind','dish','currency','rating','experience','source_key']},'price':str(a.price) if a.price is not None else None,
                           'media_ids':list(db.scalars(select(ActivityMedia.media_id).where(ActivityMedia.activity_id==a.id,ActivityMedia.active.is_(True)).order_by(ActivityMedia.media_id)))})
    photos=[{'media_id':p.media_id,'taken_on':p.taken_on.isoformat() if p.taken_on else None,'place_id':p.place_id,'group_name':p.group_name} for p in db.scalars(select(PhotoAnnotation).where(PhotoAnnotation.record_id==id,PhotoAnnotation.active.is_(True)).order_by(PhotoAnnotation.media_id))]
    return {'start_date':plan.start_date.isoformat() if plan and plan.start_date else None,'end_date':plan.end_date.isoformat() if plan and plan.end_date else None,'map_mode':plan.map_mode if plan else 'offline','activities':activities,'photos':photos}


def save_life(db,r,data,*,derive=True):
    old=life_data(db,r.id)
    # Omitted subfields are not an instruction to erase existing activities,
    # photos, or dates. Explicit []/null still use the established semantics.
    data=LifeIn.model_validate(old if data is None else old|data.model_dump(exclude_unset=True))
    if derive:
        from .content import fields_for
        # Lossless consolidation on explicit save only: conflicting historical values
        # must be resolved by the author, never guessed or overwritten.
        dates={}
        for f in fields_for(db,r.type_id,r.schema_version):
            name=f['name'];value=r.values.get(f['id'])
            k='start_date' if name in ('出发日期','旅行开始日期') else 'end_date' if name in ('返回日期','旅行结束日期') else None
            if k and f['kind']=='date' and value:
                current=getattr(data,k)
                if k in dates and dates[k]!=value:raise HTTPException(422,'存在多个不同的旅行日期字段，请明确统一来源')
                if current and current.isoformat()!=value:raise HTTPException(422,'旅行日期来源冲突，请明确选择历史字段日期或结构化日期')
                dates[k]=value
        if dates:
            try:data=LifeIn.model_validate(data.model_dump()|dates)
            except ValueError:raise HTTPException(422,'旅行日期与行程范围不一致，请核对出发、返回和活动日期') from None
    from .body_media import sync_body
    from ..content_models import RecordBodyMedia
    sync_body(db,r);db.flush()
    media=set(db.scalars(select(RecordMedia.media_id).where(RecordMedia.record_id==r.id)))
    media |= set(db.scalars(select(RecordBodyMedia.media_id).where(RecordBodyMedia.record_id==r.id)))
    places=set(db.scalars(select(RecordPlace.place_id).where(RecordPlace.record_id==r.id)))
    if r.status=='published' and data.activities and not data.start_date:raise HTTPException(422,'发布含行程的记录前请填写旅行开始日期（结束日期可留空）')
    from ..experience_models import ActivityExperience,Experience
    for a in data.activities:
        if a.experience_id:
            entry=db.get(Experience,(r.id,str(a.experience_id)))
            old_link=db.get(ActivityExperience,str(a.id))
            if not entry or entry.kind!='t' or not entry.active and not (old_link and old_link.record_id==r.id and old_link.entry_id==str(a.experience_id)):raise HTTPException(422,'行程只能引用本文章中有效的交通卡片，请先保存正文卡片')
        if a.place_id and str(a.place_id) not in places:raise HTTPException(422,'活动地点需先关联到当前记录')
        if not {str(x) for x in a.media_ids}<=media:raise HTTPException(422,'活动图片需先关联到当前记录')
        row=db.get(TripActivity,str(a.id))
        if row and row.record_id!=r.id:raise HTTPException(422,'活动不属于当前记录')
        if a.source_key:
            existing=db.scalar(select(TripActivity).where(TripActivity.record_id==r.id,TripActivity.source_key==a.source_key))
            if existing and existing.id!=str(a.id):raise HTTPException(409,'此正文活动已经同步过，不会重复追加')
        if row and row.source_key and a.source_key!=row.source_key:raise HTTPException(409,'不能改变已有活动的来源身份')
    # An unlinked photo's annotation stays in history; it is never deleted.
    for p in data.photos:
        if str(p.media_id) in media and p.place_id and str(p.place_id) not in places:raise HTTPException(422,'照片地点需先关联到当前记录')
        if str(p.media_id) not in media and not any(x['media_id']==str(p.media_id) for x in old['photos']):raise HTTPException(422,'照片信息不属于当前记录')
    # Old records with no extension do not acquire rows on ordinary edits.
    captured=derive and any(db.get(MediaAsset,mid).captured_on for mid in media)
    if not any([data.start_date,data.end_date,data.activities,data.photos,captured,db.get(TripPlan,r.id)]) and data.map_mode=='offline':return
    plan=db.get(TripPlan,r.id)
    if not plan:plan=TripPlan(record_id=r.id);db.add(plan)
    plan.start_date=data.start_date;plan.end_date=data.end_date;plan.map_mode=data.map_mode
    for row in db.scalars(select(TripActivity).where(TripActivity.record_id==r.id)):row.active=False
    for a in data.activities:
        row=db.get(TripActivity,str(a.id))
        if derive and row and row.markdown_owned:
            keys=['day','time','title','description','kind','dish','price','currency','rating','experience','place_id']
            previous=next((item for item in old['activities'] if item['id']==str(a.id)),None)
            if row.position!=data.activities.index(a) or previous and set(previous['media_ids'])!={str(mid) for mid in a.media_ids} or any(str(getattr(row,k) or '')!=str(getattr(a,k) or '') for k in keys):row.markdown_owned=False
        if not row:row=TripActivity(id=str(a.id),record_id=r.id);db.add(row)
        for key in ['day','time','title','description','kind','dish','price','currency','rating','experience','source_key']:setattr(row,key,getattr(a,key))
        row.place_id=str(a.place_id) if a.place_id else None;row.position=data.activities.index(a);row.active=True
        db.flush()
        link=db.get(ActivityExperience,row.id)
        if a.experience_id:
            if link is None:link=ActivityExperience(activity_id=row.id);db.add(link)
            link.record_id=r.id;link.entry_id=str(a.experience_id)
        elif link:db.delete(link)
        for m in db.scalars(select(ActivityMedia).where(ActivityMedia.activity_id==row.id)):m.active=False
        for id in a.media_ids:
            ref=db.get(ActivityMedia,(row.id,str(id)))
            if not ref:ref=ActivityMedia(activity_id=row.id,media_id=str(id));db.add(ref)
            ref.active=True
    for p in db.scalars(select(PhotoAnnotation).where(PhotoAnnotation.record_id==r.id)):p.active=False
    for p in data.photos:
        row=db.get(PhotoAnnotation,(r.id,str(p.media_id)))
        if not row:row=PhotoAnnotation(record_id=r.id,media_id=str(p.media_id));db.add(row)
        row.taken_on=p.taken_on;row.place_id=str(p.place_id) if p.place_id else None;row.group_name=p.group_name.strip();row.active=str(p.media_id) in media
    db.flush()

    if derive:
        # Capture dates are metadata, never inferred from upload time or GPS.
        known={str(p.media_id) for p in data.photos}
        remaining=max(0,100-sum(str(p.media_id) in media for p in data.photos))
        for mid in sorted(media-known):
            if not remaining:break
            if db.get(PhotoAnnotation,(r.id,mid)) is None:
                asset=db.get(MediaAsset,mid)
                if asset and asset.captured_on:
                    db.add(PhotoAnnotation(record_id=r.id,media_id=mid,taken_on=asset.captured_on,place_id=None,group_name='',active=True));remaining-=1
        # Draft saves and ordinary updates never regenerate an itinerary.
        # First publication and confirmed reconciliation run separately.
        db.flush()
