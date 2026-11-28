"""Explicit, previewed maintenance of derived rows. Never writes source bodies/files.

Stable food/experience identities and all manual data are retained. Only proven
redundant inactive edges can be detached; immutable snapshots remain protected.
"""
import hashlib
import json
from sqlalchemy import select
from fastapi import HTTPException
from ..content_models import ContentRecord, RecordRevision, RevisionMediaRef, RecordBodyMedia
from ..experience_models import Experience, ExperienceMedia
from ..archive_models import RevisionPlaceRef, Place, MediaAsset, RecordMarkedPlace, RecordPlace
from ..v5_models import FoodOccurrence
from ..life_models import TripActivity, TripPlan
from .archive import write_lock


def digest(db):
    # Cover every dependency, including manual overrides, travel data, schema fields
    # and revision snapshots. Return only a digest, never private table contents.
    h = hashlib.sha256()
    for table in sorted(ContentRecord.metadata.sorted_tables, key=lambda t: t.name):
        rows = [dict(row) for row in db.execute(select(table)).mappings()]
        encoded = sorted(json.dumps(row, sort_keys=True, default=str, ensure_ascii=False) for row in rows)
        h.update(json.dumps([table.name, encoded], ensure_ascii=False).encode())
    return h.hexdigest()


def state(db, rid):
    result = {}
    for model in (Experience, ExperienceMedia, FoodOccurrence, RecordBodyMedia, RecordMarkedPlace, RecordPlace, TripActivity):
        values = []
        for row in db.scalars(select(model).where(model.record_id == rid)):
            values.append({c.name: getattr(row, c.name) for c in model.__table__.columns if c.name not in ('updated_at', 'revision')})
        result[model.__tablename__] = sorted(json.dumps(x, sort_keys=True, default=str) for x in values)
    return result


def history_issues(db):
    from .places import snapshot_places
    from .resource_usage import snapshot_media_ids
    issues = []
    missing = []
    for revision in db.scalars(select(RecordRevision)):
        try:
            groups = [(Place, RevisionPlaceRef, 'place', snapshot_places(revision.snapshot)),
                      (MediaAsset, RevisionMediaRef, 'media', snapshot_media_ids(revision.snapshot))]
        except Exception:
            issues.append({'record_id': revision.record_id, 'revision': revision.number, 'code': 'invalid_snapshot'})
            continue
        for resource, ref, kind, ids in groups:
            for identity in ids:
                if db.get(resource, identity) is None:
                    issues.append({'record_id': revision.record_id, 'revision': revision.number, 'code': 'missing_history_'+kind})
                elif db.get(ref, (revision.record_id, revision.number, identity)) is None:
                    item = {'record_id': revision.record_id, 'revision': revision.number, 'resource_id': identity, 'code': 'missing_history_'+kind+'_reference'}
                    issues.append(item)
                    missing.append((ref, item, kind))
    return issues, missing


def cleanup_candidates(db):
    # Stable rows and all manual data survive; only proven redundant edges leave.
    candidates = []
    from .experiences import entries
    sources = {}
    for row in db.scalars(select(ExperienceMedia).where(ExperienceMedia.active.is_(False))):
        record = db.get(ContentRecord, row.record_id)
        if not record or record.deleted_at:
            continue  # recycle-bin restoration still owns these links
        if record.id not in sources:
            try:
                sources[record.id] = {(e['id'], mid) for e in (entries(record.body) if record.body_format == 2 else []) for mid in e['media_ids']}
            except HTTPException:
                sources[record.id] = None  # source_not_rebuildable is already reported
        if sources[record.id] is not None and (row.entry_id, row.media_id) not in sources[record.id]:
            candidates.append({'record_id':row.record_id, 'entry_id':row.entry_id, 'media_id':row.media_id})
    return sorted(candidates, key=lambda x: tuple(x.values()))


def food_detach_candidates(db):
    from .experiences import entries
    from .places import canonical
    candidates=[]
    for row in db.scalars(select(FoodOccurrence).where(FoodOccurrence.active.is_(False),FoodOccurrence.place_id.is_not(None))):
        record=db.get(ContentRecord,row.record_id)
        if not record or record.deleted_at or not row.source_key.startswith('entry:'):
            continue
        entry_id=row.source_key[6:]
        try:
            current=entries(record.body) if record.body_format==2 else []
        except HTTPException:
            continue  # never detach when the authoritative source cannot be parsed
        if any(e['id']==entry_id for e in current):
            continue
        # An immutable, recoverable snapshot must prove the original association.
        proven=False
        for revision in db.scalars(select(RecordRevision).where(RecordRevision.record_id==record.id)):
            snapshot=revision.snapshot
            if not isinstance(snapshot,dict) or snapshot.get('body_format',1)!=2:continue
            try:
                historical=entries(snapshot.get('body',''))
            except HTTPException:
                continue  # invalid_snapshot is already reported; preserve the edge
            for entry in historical:
                pid=entry['fields'].get('place_id')
                if entry['id']==entry_id and entry['kind']=='f' and pid and canonical(db,pid)==row.place_id and db.get(Place,pid):
                    proven=True
        if proven:candidates.append({'id':row.id,'record_id':row.record_id,'place_id':row.place_id,'expected_revision':row.revision})
    return sorted(candidates,key=lambda x:x['id'])


def sync_record(db, record):
    from . import experiences, food, body_media, marked_places
    if not record.deleted_at:
        places_before=set(db.scalars(select(Place.id)))
        resolved=marked_places.sync(db,record)
        if set(db.scalars(select(Place.id)))!=places_before:
            raise HTTPException(409,'缺少可证明的原地点绑定，禁止重建时创建新地点身份')
        plan=db.get(TripPlan,record.id)
        if plan:marked_places.sync_activities(db,record,plan,resolved)
        marked_places.prune_connections(db,record)
    experiences.sync(db,record)
    food.sync(db,record)
    body_media.sync_body(db,record)
    db.flush()


def preview(db):
    token = digest(db)
    issues, missing = history_issues(db)
    changed = []
    for record in db.scalars(select(ContentRecord).order_by(ContentRecord.id)).all():
        before = state(db, record.id)
        savepoint = db.begin_nested()
        try:
            sync_record(db, record)
            after = state(db, record.id)
            if before != after:
                changed.append({'record_id':record.id, 'expected_revision':record.revision, 'indexes':[k for k in before if before[k]!=after[k]]})
        except HTTPException as exc:
            issues.append({'record_id':record.id, 'code':'source_not_rebuildable', 'status':exc.status_code})
        finally:
            savepoint.rollback()
    candidates = cleanup_candidates(db)
    detach = food_detach_candidates(db)
    detachable = {item['id'] for item in detach}
    for model in (Experience, FoodOccurrence, TripActivity):
        for row in db.scalars(select(model).outerjoin(ContentRecord,ContentRecord.id==model.record_id).where(ContentRecord.id.is_(None))):
            issues.append({'record_id':row.record_id,'code':'missing_source_record','index':model.__tablename__})
    return {'digest':token, 'records':changed, 'issues':issues,
            'history_references_to_add':len(missing), 'cleanup':candidates, 'food_detach':detach,
            'preserved_food_identities':len(db.scalars(select(FoodOccurrence).where(FoodOccurrence.active.is_(False))).all()),
            'blocked_food':[{'id':row.id,'record_id':row.record_id,'reason':'无不可变快照证明，或来源仍存在/处于回收站；保留地点关联及身份'} for row in db.scalars(select(FoodOccurrence).where(FoodOccurrence.active.is_(False),FoodOccurrence.place_id.is_not(None))) if row.id not in detachable],
            'note':'稳定身份、手动城市与分类保留；仅解除有不可变历史快照证明的失效美食地点关联，及可重建卡片媒体关联。历史、正文和原图保留。'}


def apply(db, expected_digest, action):
    if action not in ('rebuild','cleanup'):
        raise HTTPException(422,'索引维护操作无效')
    write_lock(db)
    if digest(db) != expected_digest:
        raise HTTPException(409, '资源或正文已变化，请重新预览；未执行维护')
    plan = preview(db)
    if any(i['code'] in ('source_not_rebuildable','invalid_snapshot','missing_history_place','missing_history_media','missing_source_record') for i in plan['issues']):
        raise HTTPException(409, {'message':'存在无法安全重建的来源，请先修复；未执行维护', 'issues':plan['issues']})
    if action == 'rebuild':
        for item in plan['records']:
            record = db.get(ContentRecord, item['record_id'])
            sync_record(db, record)
    # Repair additive history protection before removing any derived links.
    _, missing = history_issues(db)
    for model, item, kind in missing:
        db.add(model(record_id=item['record_id'], number=item['revision'], **{kind+'_id':item['resource_id']}))
    db.flush()
    if action == 'cleanup':
        for item in plan['food_detach']:
            row=db.get(FoodOccurrence,item['id'])
            row.place_id=None
            row.revision+=1
        for item in plan['cleanup']:
            db.delete(db.get(ExperienceMedia, tuple(item.values())))
    db.flush()
    db.commit()
    return {'ok':True, 'action':action, 'records':len(plan['records']) if action=='rebuild' else 0,
            'cleaned':len(plan['cleanup'])+len(plan['food_detach']) if action=='cleanup' else 0, 'history_references_added':len(missing)}
