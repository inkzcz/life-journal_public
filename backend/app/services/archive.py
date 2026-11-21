"""Archive transactions share one short PostgreSQL lock (low-volume personal writes).
It serializes reference changes against soft-delete, including reciprocal graph edits.
"""
from sqlalchemy import select, delete, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Load,undefer
from fastapi import HTTPException
from ..archive_models import MediaAsset, Place, RecordMedia, RecordLink, RecordPlace
from ..content_models import ContentRecord

def write_lock(db):
    if db.bind.dialect.name=='sqlite':
        # pysqlite defers BEGIN until DML. Claim the writer before identity reads,
        # while preserving an already-open transaction and every nested caller.
        if not db.connection().connection.driver_connection.in_transaction:
            try:db.execute(text('BEGIN IMMEDIATE'))
            except OperationalError:
                db.rollback();raise HTTPException(409,'其他页面正在保存关联资源，请稍后重试') from None
    elif db.bind.dialect.name=='postgresql':
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        try:
            db.execute(text('SELECT pg_advisory_xact_lock(721934004)'))
        except OperationalError as exc:
            if getattr(exc.orig,'sqlstate',None)=='55P03':
                db.rollback();raise HTTPException(409,'其他页面正在保存关联资源，请稍后重试') from None
            raise

def asset_data(m):
    return {k:getattr(m,k) for k in ['folder_id','category','id','filename','mime_type','size','width','height','sha256','preview_sha256','preview_width','preview_height','thumbnail_sha256','title','description','alt','uploaded_by','revision']} | {'created_at':m.created_at.isoformat(),'captured_on':m.captured_on.isoformat() if m.captured_on else None}

def place_data(p):
    return {k:getattr(p,k) for k in ['id','name','country','region','city','address','category','notes','active','revision']} | {'latitude':str(p.latitude) if p.latitude is not None else None,'longitude':str(p.longitude) if p.longitude is not None else None,'created_at':p.created_at.isoformat(),'updated_at':p.updated_at.isoformat()}

def asset(db,id):
    m=db.get(MediaAsset,str(id))
    if m is None or m.deleted_at:raise HTTPException(404,'图片不存在')
    return m

def place(db,id):
    p=db.get(Place,str(id))
    if p is None:raise HTTPException(404,'地点不存在')
    return p

def record_ref(r):
    return {'id':r.id,'title':r.title,'deleted':r.deleted_at is not None,'type_id':r.type_id}

def connections_data(db,id):
    media=[]
    for ref,m in db.execute(select(RecordMedia,MediaAsset).options(Load(MediaAsset).undefer_group('media_management')).join(MediaAsset,RecordMedia.media_id==MediaAsset.id).where(RecordMedia.record_id==id).order_by(RecordMedia.position)):
        media.append({'id':m.id,'cover':ref.cover,'caption':ref.caption,'asset':asset_data(m)})
    links=[{**record_ref(r),'label':ref.label} for ref,r in db.execute(select(RecordLink,ContentRecord).join(ContentRecord,RecordLink.target_id==ContentRecord.id).where(RecordLink.source_id==id).order_by(RecordLink.label,RecordLink.target_id))]
    incoming=[{**record_ref(r),'label':ref.label} for ref,r in db.execute(select(RecordLink,ContentRecord).join(ContentRecord,RecordLink.source_id==ContentRecord.id).where(RecordLink.target_id==id).order_by(RecordLink.label,RecordLink.source_id))]
    places=[place_data(p) for p in db.scalars(select(Place).join(RecordPlace,RecordPlace.place_id==Place.id).where(RecordPlace.record_id==id).order_by(Place.name,Place.id))]
    return {'media':media,'links':links,'places':places,'incoming':incoming}

def replace_connections(db,record,data):
    if data is None:return
    # Caller acquires write_lock BEFORE updating/locking any record or resource.
    old_links=set(db.execute(select(RecordLink.target_id,RecordLink.label).where(RecordLink.source_id==record.id)))
    old_place_flags={p.place_id:p.markdown_owned for p in db.scalars(select(RecordPlace).options(undefer(RecordPlace.markdown_owned)).where(RecordPlace.record_id==record.id))}
    old_places=set(old_place_flags)
    for item in data.media:
        asset(db,item.id)
    for item in data.links:
        target=db.get(ContentRecord,str(item.id))
        if str(item.id)==record.id:raise HTTPException(422,'不能关联自身')
        if target is None or (target.deleted_at and (str(item.id),item.label) not in old_links):raise HTTPException(422,'不能新增指向不存在或已删除记录的关联')
    for id in data.places:
        p=place(db,id)
        if not p.active and p.id not in old_places:raise HTTPException(422,'不能新增已停用地点')
    for model,column in [(RecordMedia,RecordMedia.record_id),(RecordLink,RecordLink.source_id),(RecordPlace,RecordPlace.record_id)]:
        db.execute(delete(model).where(column==record.id))
    db.flush()
    for i,item in enumerate(data.media):db.add(RecordMedia(record_id=record.id,media_id=str(item.id),position=i,cover=item.cover,caption=item.caption))
    for item in data.links:db.add(RecordLink(source_id=record.id,target_id=str(item.id),label=item.label))
    for id in data.places:db.add(RecordPlace(record_id=record.id,place_id=str(id),markdown_owned=old_place_flags.get(str(id),False)))
    db.flush()
