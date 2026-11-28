"""Explicit, previewed maintenance of derived rows. Never writes source bodies/files.

Stable food/experience identities and all manual data are retained. Only proven
redundant inactive edges can be detached; immutable snapshots remain protected.
"""
import hashlib
import json
from threading import Lock
from collections import defaultdict, OrderedDict
from types import SimpleNamespace
from sqlalchemy.orm import undefer
from sqlalchemy import select
from fastapi import HTTPException
from ..content_models import ContentRecord, RecordRevision, RevisionMediaRef, RecordBodyMedia
from ..experience_models import Experience, ExperienceMedia
from ..archive_models import RevisionPlaceRef, Place, PlaceAlias, MediaAsset, ResourceReferenceAudit, RecordMarkedPlace, RecordPlace
from ..v5_models import FoodOccurrence
from ..life_models import TripActivity, TripPlan
from .archive import write_lock


_STATE_MODELS = (Experience, ExperienceMedia, FoodOccurrence, RecordBodyMedia, RecordMarkedPlace, RecordPlace, TripActivity)
# Cache only hashes and diagnostic/index names, never bodies, snapshots or manual
# values. Every production synchronizer dependency participates in the key.
_OUTCOMES = OrderedDict()
_MAX_OUTCOMES = 4096
_OUTCOME_LOCK = Lock()

def cached_outcome(key):
    with _OUTCOME_LOCK:
        outcome=_OUTCOMES.get(key)
        if outcome is not None:_OUTCOMES.move_to_end(key)
        return outcome

def remember_outcome(key,outcome):
    with _OUTCOME_LOCK:
        _OUTCOMES[key]=outcome
        _OUTCOMES.move_to_end(key)
        if len(_OUTCOMES)>_MAX_OUTCOMES:_OUTCOMES.popitem(last=False)


def database_snapshot(db):
    return {table.name:[dict(row) for row in db.execute(select(table)).mappings()]
            for table in sorted(ContentRecord.metadata.sorted_tables,key=lambda t:t.name)}


def encoded(value):
    return json.dumps(value,sort_keys=True,default=str,ensure_ascii=False)


def snapshot_digest(snapshot):
    h=hashlib.sha256()
    for name,rows in sorted(snapshot.items()):
        h.update(json.dumps([name,sorted(encoded(row) for row in rows)],ensure_ascii=False).encode())
    return h.hexdigest()


def digest(db):
    # Complete CAS remains byte-for-byte equivalent to the original whole-DB gate.
    return snapshot_digest(database_snapshot(db))


def project(rows):
    return sorted(json.dumps({k:v for k,v in row.items() if k not in ('updated_at','revision')},sort_keys=True,default=str) for row in rows)


def state(db, rid):
    # Core projections include deferred columns in one query per table.
    return {model.__tablename__:project(db.execute(select(model.__table__).where(model.__table__.c.record_id==rid)).mappings())
            for model in _STATE_MODELS}


def dependency_keys(snapshot):
    records=defaultdict(list); types=defaultdict(list); globals=[]
    for name,rows in snapshot.items():
        table=ContentRecord.metadata.tables[name]
        if name=='content_records':
            for row in rows:records[row['id']].append((name,encoded(row)))
        elif 'record_id' in table.c:
            for row in rows:records[row['record_id']].append((name,encoded(row)))
        elif 'type_id' in table.c:
            for row in rows:types[row['type_id']].append((name,encoded(row)))
        elif name=='content_types':
            for row in rows:types[row['id']].append((name,encoded(row)))
        elif name in {model.__tablename__ for model in (Place,PlaceAlias,MediaAsset,ResourceReferenceAudit)}:
            # The synchronizers never read auth/session/album/job tables. These
            # remain in full CAS but cannot affect a per-record projection.
            globals.append((name,sorted(encoded(row) for row in rows)))
    common=hashlib.sha256(encoded(globals).encode()).hexdigest()
    return common,records,types


def inert_record(record, before, snapshot):
    # Exact empty-output proof: no parser trigger, existing index/resource edge,
    # travel plan, food type, or private-media field can generate derived data.
    if record.body_format not in (1,2) or '@' in record.body or ':::lj-' in record.body or 'library-media/' in record.body:
        return False
    if 'library-media/' in encoded(record.values):return False
    # Independent manual associations and already-inactive identity rows are
    # untouched by production sync when there is no authored parser source.
    rows={name:[json.loads(value) for value in values] for name,values in before.items()}
    if any(row['active'] for name in ('experiences','experience_media','food_occurrences') for row in rows[name]):return False
    if rows['record_body_media']:return False
    if not record.deleted_at:
        if rows['record_marked_places'] or any(row['markdown_owned'] for row in rows['record_places']):return False
        for activity in rows['trip_activities']:
            if activity['active'] and (activity['markdown_owned'] or activity['kind']=='food'):return False
        if any(row['type_id']==record.type_id for row in snapshot['food_content_types']):return False
    return any(row['type_id']==record.type_id and row['number']==record.schema_version for row in snapshot['content_type_versions'])


def history_issues(db, snapshot=None):
    from .places import snapshot_places
    from .resource_usage import snapshot_media_ids
    issues = []
    missing = []
    if snapshot is None:snapshot=database_snapshot(db)
    place_ids={row['id'] for row in snapshot['places']}
    media_ids={row['id'] for row in snapshot['media_assets']}
    place_refs={(row['record_id'],row['number'],row['place_id']) for row in snapshot[RevisionPlaceRef.__tablename__]}
    media_refs={(row['record_id'],row['number'],row['media_id']) for row in snapshot[RevisionMediaRef.__tablename__]}
    for data in snapshot[RecordRevision.__tablename__]:
        revision=SimpleNamespace(**data)
        try:
            groups = [(Place, RevisionPlaceRef, 'place', snapshot_places(revision.snapshot)),
                      (MediaAsset, RevisionMediaRef, 'media', snapshot_media_ids(revision.snapshot))]
        except Exception:
            issues.append({'record_id': revision.record_id, 'revision': revision.number, 'code': 'invalid_snapshot'})
            continue
        for resource, ref, kind, ids in groups:
            for identity in ids:
                if identity not in (place_ids if kind=='place' else media_ids):
                    issues.append({'record_id': revision.record_id, 'revision': revision.number, 'code': 'missing_history_'+kind})
                elif (revision.record_id,revision.number,identity) not in (place_refs if kind=='place' else media_refs):
                    item = {'record_id': revision.record_id, 'revision': revision.number, 'resource_id': identity, 'code': 'missing_history_'+kind+'_reference'}
                    issues.append(item)
                    missing.append((ref, item, kind))
    return issues, missing


def cleanup_candidates(db, records=None):
    # Stable rows and all manual data survive; only proven redundant edges leave.
    candidates = []
    from .experiences import entries
    sources = {}
    for row in db.scalars(select(ExperienceMedia).where(ExperienceMedia.active.is_(False))):
        record = records.get(row.record_id) if records is not None else db.get(ContentRecord, row.record_id)
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


def food_detach_candidates(db, records=None, snapshot=None):
    from .experiences import entries
    from .places import canonical
    candidates=[]
    if snapshot is None:snapshot=database_snapshot(db)
    revisions=defaultdict(list)
    for revision in snapshot[RecordRevision.__tablename__]:revisions[revision['record_id']].append(revision)
    place_ids={place['id'] for place in snapshot['places']}
    aliases={alias['source_id']:alias['target_id'] for alias in snapshot['place_aliases']}
    def resolve(identity):
        seen=set()
        while identity in aliases:
            if identity in seen:raise HTTPException(409,'地点别名循环，停止操作')
            seen.add(identity);identity=aliases[identity]
        return identity
    proven_sources={}
    current_sources={}
    for row in db.scalars(select(FoodOccurrence).where(FoodOccurrence.active.is_(False),FoodOccurrence.place_id.is_not(None))):
        record=records.get(row.record_id) if records is not None else db.get(ContentRecord,row.record_id)
        if not record or record.deleted_at or not row.source_key.startswith('entry:'):
            continue
        entry_id=row.source_key[6:]
        if record.id not in current_sources:
            try:current_sources[record.id]={e['id'] for e in (entries(record.body) if record.body_format==2 else [])}
            except HTTPException:current_sources[record.id]=None
        current=current_sources[record.id]
        if current is None or entry_id in current:continue
        if record.id not in proven_sources:
            proven_sources[record.id]=set()
            for revision in revisions[record.id]:
                saved=revision['snapshot']
                if not isinstance(saved,dict) or saved.get('body_format',1)!=2:continue
                try:historical=entries(saved.get('body',''))
                except HTTPException:continue
                for entry in historical:
                    pid=entry['fields'].get('place_id')
                    if entry['kind']=='f' and pid in place_ids:
                        proven_sources[record.id].add((entry['id'],resolve(pid)))
        if (entry_id,row.place_id) in proven_sources[record.id]:candidates.append({'id':row.id,'record_id':row.record_id,'place_id':row.place_id,'expected_revision':row.revision})
    return sorted(candidates,key=lambda x:x['id'])


def sync_record(db, record):
    from . import experiences, food, body_media, marked_places
    if not record.deleted_at:
        # Maintenance must never infer an identity from today's catalog names.
        # An existing resource can have inherited an old name after a rename.
        bindings=dict(db.execute(select(RecordMarkedPlace.source_key,RecordMarkedPlace.place_id).where(RecordMarkedPlace.record_id==record.id)).all())
        for mark in marked_places.document(db,record).marks:
            if not mark.get('place_id') and not bindings.get(marked_places.key(mark,mark['region'])):
                raise HTTPException(409,{'code':'missing_legacy_place_binding','message':'旧版标记缺少稳定地点绑定；请明确选择原地点 UUID 后再重建，不能按当前同名地点推断身份'})
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
    # Simulations and their cache keys must observe one serialized source state.
    # This transaction lock writes no source data and is released by the caller.
    write_lock(db)
    db.info.pop('food_fields',None)
    snapshot=database_snapshot(db)
    token=snapshot_digest(snapshot)
    issues,missing=history_issues(db,snapshot)
    common,dependencies,type_dependencies=dependency_keys(snapshot)
    indexed={model.__tablename__:defaultdict(list) for model in _STATE_MODELS}
    for name,groups in indexed.items():
        for row in snapshot[name]:groups[row['record_id']].append(row)
    changed=[]
    records=db.scalars(select(ContentRecord).options(undefer('*')).order_by(ContentRecord.id)).all()
    for record in records:
        before={name:project(groups.get(record.id,[])) for name,groups in indexed.items()}
        if inert_record(record,before,snapshot):continue
        key=hashlib.sha256(encoded([db.bind.dialect.name,common,sorted(dependencies[record.id]),sorted(type_dependencies[record.type_id])]).encode()).hexdigest()
        outcome=cached_outcome(key)
        if outcome is None:
            savepoint=db.begin_nested()
            try:
                sync_record(db,record)
                after=state(db,record.id)
                outcome={'indexes':[name for name in before if before[name]!=after[name]]}
            except HTTPException as exc:
                outcome={'status':exc.status_code}
                if isinstance(exc.detail,dict) and exc.detail.get('code')=='missing_legacy_place_binding':
                    outcome['reason']='missing_legacy_place_binding'
            finally:
                savepoint.rollback()
            remember_outcome(key,outcome)
        if 'status' in outcome:
            issues.append({'record_id':record.id,'code':'source_not_rebuildable','status':outcome['status'],**({'reason':outcome['reason']} if 'reason' in outcome else {})})
        elif outcome['indexes']:
            changed.append({'record_id':record.id,'expected_revision':record.revision,'indexes':outcome['indexes']})
    record_map={record.id:record for record in records}
    candidates = cleanup_candidates(db,record_map)
    detach = food_detach_candidates(db,record_map,snapshot)
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
