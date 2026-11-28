"""Synthetic lifecycle coverage; uses the shared SQLite/PostgreSQL test harness."""
import copy
from sqlalchemy import select
from test_content import client,make_type,record_payload,update_payload,write
from test_archive import upload
from test_api import SessionLocal,csrf,reset_limiter
from test_experiences import card
from test_places_management import place
from app.services.experiences import serialize
from app.services.index_lifecycle import preview,digest
from app.experience_models import Experience,ExperienceMedia
from app.v5_models import FoodOccurrence
from app.content_models import ContentRecord,RecordRevision,RevisionMediaRef

URL='/api/admin/archive/places/maintenance/'
def inspect(c):
    response=c.get(URL+'index-preview');assert response.status_code==200,response.text;return response.json()
def apply(c,plan,action='rebuild'):
    return c.post(URL+'index-apply',headers=csrf(c),json={'digest':plan['digest'],'action':action,'confirmation':'确认索引维护'})
def record(c,e):
    return write(c,'/records',{**record_payload(make_type(c)),'body_format':2,'body':serialize(e)}).json()

def test_categories_distinct_counts_and_conservative_cleanup(client):
    p=place(client);m=upload(client).json();e=card('f',fields={'place_id':p['id']},media_ids=[m['id']]);r=record(client,e)
    detail=client.get('/api/admin/archive/places/'+p['id']).json()
    assert detail['usage_counts']['current']==1 and detail['usage_counts']['history']==1
    r=write(client,'/records/'+r['id'],update_payload(r,body='合成普通正文'),'put').json()
    with SessionLocal() as db:
        food=db.scalar(select(FoodOccurrence).where(FoodOccurrence.record_id==r['id']))
        food.city_override='手动合成城市';food.category='手动分类';identity=food.id;db.commit()
        snapshot=copy.deepcopy(db.get(RecordRevision,(r['id'],1)).snapshot)
    detail=client.get('/api/admin/archive/places/'+p['id']).json()
    assert detail['usage_counts']['current']==0 and detail['usage_counts']['inactive']==1
    plan=inspect(client)
    assert any(x['id']==identity for x in plan['food_detach'])
    assert apply(client,plan,'cleanup').status_code==200
    with SessionLocal() as db:
        food=db.get(FoodOccurrence,identity)
        assert food.place_id is None and food.city_override=='手动合成城市' and food.category=='手动分类'
        assert food.source_key=='entry:'+e['id'] and not food.active
        assert db.get(RecordRevision,(r['id'],1)).snapshot==snapshot
        assert db.get(ExperienceMedia,(r['id'],e['id'],m['id'])) is None
        assert db.get(RevisionMediaRef,(r['id'],1,m['id'])) is not None
    assert client.request('DELETE','/api/admin/archive/places/'+p['id'],headers=csrf(client),json={'expected_revision':p['revision']}).status_code==409
    # Restoring the same source reuses the UUID and independent manual values.
    r=write(client,'/records/'+r['id'],update_payload(r,body=serialize(e)),'put').json()
    with SessionLocal() as db:
        food=db.get(FoodOccurrence,identity)
        assert food.active and food.place_id==p['id'] and food.city_override=='手动合成城市'


def test_readonly_audit_missing_stale_and_digest_cas(client):
    e=card();r=record(client,e)
    with SessionLocal() as db:
        db.get(Experience,(r['id'],e['id'])).active=False;db.commit()
        before=digest(db);report=preview(db)
        assert digest(db)==before
        assert any(x['record_id']==r['id'] for x in report['records'])
        assert not db.get(Experience,(r['id'],e['id'])).active
    plan=inspect(client)
    r=write(client,'/records/'+r['id'],update_payload(r,title='合成并发新标题'),'put').json()
    assert apply(client,plan).status_code==409
    with SessionLocal() as db:
        db.get(Experience,(r['id'],e['id'])).active=False;db.commit()
    plan=inspect(client);assert apply(client,plan).status_code==200
    assert not inspect(client)['records']
    assert apply(client,inspect(client)).status_code==200
    with SessionLocal() as db:
        assert db.get(ContentRecord,r['id']).body==serialize(e)
        assert db.get(Experience,(r['id'],e['id'])).active


def test_trash_not_current_and_maintenance_requires_csrf(client):
    p=place(client);r=record(client,card('l',fields={'place_id':p['id']}))
    assert write(client,'/records/'+r['id'],{'expected_revision':r['revision']},'delete').status_code==200
    detail=client.get('/api/admin/archive/places/'+p['id']).json()
    assert detail['usage_counts']['current']==0 and detail['usage_counts']['trash']==1
    plan=inspect(client)
    assert client.post(URL+'index-apply',json={'digest':plan['digest'],'action':'cleanup','confirmation':'确认索引维护'}).status_code==403


def test_history_protection_survives_missing_derived_refs_and_rebuild_adds_them(client):
    from app.archive_models import RevisionPlaceRef
    p=place(client);m=upload(client).json();e=card('f',fields={'place_id':p['id']},media_ids=[m['id']]);r=record(client,e)
    r=write(client,'/records/'+r['id'],update_payload(r,body='新的合成正文'),'put').json()
    with SessionLocal() as db:
        snapshot=copy.deepcopy(db.get(RecordRevision,(r['id'],1)).snapshot)
        db.delete(db.get(RevisionMediaRef,(r['id'],1,m['id'])))
        db.delete(db.get(RevisionPlaceRef,(r['id'],1,p['id'])))
        db.commit()
    for route,identity in [('media',m['id']),('places',p['id'])]:
        response=client.get('/api/admin/archive/'+route+'/'+identity)
        assert response.status_code==200,response.text
        assert response.json()['usage_counts']['history']==1
    plan=inspect(client)
    assert plan['history_references_to_add']>=2
    result=apply(client,plan);assert result.status_code==200,result.text
    with SessionLocal() as db:
        assert db.get(RevisionMediaRef,(r['id'],1,m['id']))
        assert db.get(RevisionPlaceRef,(r['id'],1,p['id']))
        assert db.get(RecordRevision,(r['id'],1)).snapshot==snapshot


import pytest
@pytest.mark.parametrize('kind',list('lfmsgt'))
def test_rebuild_missing_index_for_each_card_kind_preserves_source_and_history(client,kind):
    e=card(kind);r=write(client,'/records',{**record_payload(make_type(client)),'status':'draft','body_format':2,'body':serialize(e)}).json()
    with SessionLocal() as db:
        original=copy.deepcopy(db.get(RecordRevision,(r['id'],1)).snapshot)
        db.delete(db.get(Experience,(r['id'],e['id'])));db.commit()
    plan=inspect(client)
    assert any(item['record_id']==r['id'] and 'experiences' in item['indexes'] for item in plan['records'])
    response=apply(client,plan);assert response.status_code==200,response.text
    with SessionLocal() as db:
        restored=db.get(Experience,(r['id'],e['id']))
        assert restored.active and restored.kind==kind
        assert db.get(ContentRecord,r['id']).body==serialize(e)
        assert db.get(RecordRevision,(r['id'],1)).snapshot==original


def test_unprovable_inactive_food_binding_stays_protected(client):
    p=place(client);e=card('f',fields={'place_id':p['id']});r=record(client,e)
    r=write(client,'/records/'+r['id'],update_payload(r,body='合成无卡片正文'),'put').json()
    with SessionLocal() as db:
        food=db.scalar(select(FoodOccurrence).where(FoodOccurrence.record_id==r['id']))
        food.source_key='mark:unprovable:1';food.city_override='保留手动城市';identity=food.id;db.commit()
    plan=inspect(client)
    assert identity in {item['id'] for item in plan['blocked_food']}
    assert identity not in {item['id'] for item in plan['food_detach']}
    response=apply(client,plan,'cleanup');assert response.status_code==200,response.text
    with SessionLocal() as db:
        row=db.get(FoodOccurrence,identity)
        assert row.place_id==p['id'] and row.city_override=='保留手动城市' and row.source_key=='mark:unprovable:1'


def test_unrebuildable_source_fails_closed_without_partial_repairs(client):
    e=card('m');r=record(client,e)
    with SessionLocal() as db:
        db.get(ContentRecord,r['id']).body=serialize({**e,'kind':'f'});db.commit()
        before=digest(db)
    plan=inspect(client)
    assert any(item['record_id']==r['id'] and item['code']=='source_not_rebuildable' for item in plan['issues'])
    assert apply(client,plan).status_code==409
    with SessionLocal() as db:
        assert digest(db)==before
        assert db.get(Experience,(r['id'],e['id'])).kind=='m'


def test_malformed_sources_keep_candidate_edges_and_return_audit_diagnostics(client):
    p=place(client);m=upload(client).json();e=card('f',fields={'place_id':p['id']},media_ids=[m['id']]);r=record(client,e)
    r=write(client,'/records/'+r['id'],update_payload(r,body='合成移除卡片'),'put').json()
    malformed=':::lj-entry-v1\ninvalid\n:::'
    with SessionLocal() as db:
        original_body=db.get(ContentRecord,r['id']).body
        db.get(ContentRecord,r['id']).body=malformed
        revision=db.get(RecordRevision,(r['id'],2))
        original_snapshot=copy.deepcopy(revision.snapshot)
        revision.snapshot={**revision.snapshot,'body':malformed}
        db.commit()
    plan=inspect(client)
    assert any(item['record_id']==r['id'] and item['code']=='invalid_snapshot' for item in plan['issues'])
    assert any(item['record_id']==r['id'] and item['code']=='source_not_rebuildable' for item in plan['issues'])
    assert all(item['record_id']!=r['id'] for item in plan['cleanup']+plan['food_detach'])
    assert apply(client,plan,'cleanup').status_code==409
    with SessionLocal() as db:
        assert db.get(ExperienceMedia,(r['id'],e['id'],m['id']))
        assert db.scalar(select(FoodOccurrence).where(FoodOccurrence.record_id==r['id'])).place_id==p['id']
    for kind,identity in [('media',m['id']),('places',p['id'])]:
        response=client.get('/api/admin/archive/'+kind+'/'+identity)
        assert response.status_code==200,response.text
        assert response.json()['usage_counts']['system']>=1
    # The suite intentionally shares a database; repair deliberate corruption.
    with SessionLocal() as db:
        db.get(ContentRecord,r['id']).body=original_body
        db.get(RecordRevision,(r['id'],2)).snapshot=original_snapshot
        db.commit()


def test_bulk_preview_avoids_per_inert_record_queries_and_matches_production(client,monkeypatch):
    import uuid,time
    from datetime import date
    from sqlalchemy import event
    from app.services import index_lifecycle as lifecycle
    from app.archive_models import RecordPlace
    t=make_type(client);p=place(client);ids=[]
    with SessionLocal() as db:
        for index in range(250):
            identity=str(uuid.uuid4());ids.append(identity)
            db.add(ContentRecord(id=identity,type_id=t['id'],schema_version=t['revision'],title='合成批量检查',body='普通合成正文 '+str(index),body_format=2,values={},display_date=date(2026,1,1),status='draft',revision=1))
        db.flush()
        for identity in ids[:3]:
            db.add(RecordPlace(record_id=identity,place_id=p['id'],markdown_owned=False))
            db.add(Experience(record_id=identity,id=str(uuid.uuid4()),kind='g',name='合成保留身份',fields={'future_meta':'未知历史数据'},position=0,active=False))
            db.add(FoodOccurrence(id=str(uuid.uuid4()),record_id=identity,source_key='retained:manual',source_kind='mark',name='合成独立手动数据',place_id=p['id'],city_override='手动城市',category='手动分类',active=False))
        db.commit()
        # Warm complex preexisting fixtures; all 250 new records require no writes.
        lifecycle.preview(db)
        calls=[]
        original=lifecycle.sync_record
        def tracked(session,record):
            calls.append(record.id);return original(session,record)
        monkeypatch.setattr(lifecycle,'sync_record',tracked)
        statements=[]
        def capture(*args):statements.append(args[2])
        event.listen(db.bind,'before_cursor_execute',capture)
        start=time.monotonic()
        try:report=lifecycle.preview(db)
        finally:event.remove(db.bind,'before_cursor_execute',capture)
        assert not set(ids)&set(calls)
        assert not set(ids)&{item['record_id'] for item in report['records']}
        # Fixed whole-DB snapshot queries remain; no 7/14 SELECTs per article.
        assert len(statements)<len(ContentRecord.metadata.tables)+30
        for identity in ids[:3]:
            before=lifecycle.state(db,identity)
            savepoint=db.begin_nested()
            try:
                original(db,db.get(ContentRecord,identity))
                assert lifecycle.state(db,identity)==before
            finally:savepoint.rollback()
        print(f'bulk250 warm preview: {len(statements)} statements, {time.monotonic()-start:.3f}s')


def test_audit_outcome_cache_invalidates_body_manual_history_schema_without_revision(client,monkeypatch):
    from test_content import field
    from app.content_models import VersionField
    from app.services import index_lifecycle as lifecycle
    t=make_type(client,[field()]);p=place(client);m=upload(client).json();e=card('f',fields={'place_id':p['id'],'future_meta':'合成未知历史字段'},media_ids=[m['id']])
    r=write(client,'/records',{**record_payload(t),'body_format':2,'body':serialize(e)}).json()
    calls=[];original=lifecycle.sync_record
    def tracked(db,record):
        if record.id==r['id']:calls.append(record.id)
        return original(db,record)
    monkeypatch.setattr(lifecycle,'sync_record',tracked)
    with SessionLocal() as db:
        lifecycle.preview(db);assert len(calls)==1
        lifecycle.preview(db);assert len(calls)==1
        source=db.get(ContentRecord,r['id']);revision=source.revision
        source.body+='\n\n合成追加正文';db.commit()
        lifecycle.preview(db);assert len(calls)==2
        food=db.scalar(select(FoodOccurrence).where(FoodOccurrence.record_id==r['id']))
        food.city_override='合成手动覆盖';food.category='合成自定义分类';db.commit()
        lifecycle.preview(db);assert len(calls)==3
        history=db.get(RecordRevision,(r['id'],1));history.snapshot={**history.snapshot,'summary':'合成历史快照变更'};db.commit()
        lifecycle.preview(db);assert len(calls)==4
        schema=db.scalar(select(VersionField).where(VersionField.type_id==t['id']))
        schema.name='合成字段新名称';db.commit()
        lifecycle.preview(db);assert len(calls)==5
        from app.archive_models import Place,MediaAsset
        from app.models import now
        resource=db.get(Place,p['id']);resource.active=False;db.commit()
        failed=lifecycle.preview(db);assert len(calls)==6
        assert any(item.get('record_id')==r['id'] and item['code']=='source_not_rebuildable' for item in failed['issues'])
        resource.active=True
        media=db.get(MediaAsset,m['id']);media.deleted_at=now();db.commit()
        failed=lifecycle.preview(db);assert len(calls)==7
        assert any(item.get('record_id')==r['id'] and item['code']=='source_not_rebuildable' for item in failed['issues'])
        media.deleted_at=None;db.commit()
        lifecycle.preview(db);assert len(calls)==7  # exact restored dependency key safely reuses its outcome
        restored_body=db.get(ContentRecord,r['id']).body
        db.get(ContentRecord,r['id']).body=serialize({**e,'kind':'m'})
        db.flush()
        failed=lifecycle.preview(db);assert len(calls)==8
        assert any(item.get('record_id')==r['id'] and item['code']=='source_not_rebuildable' for item in failed['issues'])
        db.rollback()
        lifecycle.preview(db);assert len(calls)==8
        assert db.get(ContentRecord,r['id']).body==restored_body
        assert db.get(ContentRecord,r['id']).revision==revision
        assert food.city_override=='合成手动覆盖' and food.category=='合成自定义分类'
        assert food.source_key=='entry:'+e['id']
        assert db.get(Experience,(r['id'],e['id'])).fields['future_meta']=='合成未知历史字段'


def test_outcome_cache_concurrent_eviction_is_bounded_and_atomic(monkeypatch):
    import hashlib
    from concurrent.futures import ThreadPoolExecutor
    from app.services import index_lifecycle as lifecycle
    monkeypatch.setattr(lifecycle,'_MAX_OUTCOMES',8)
    with lifecycle._OUTCOME_LOCK:lifecycle._OUTCOMES.clear()
    def exercise(worker):
        for index in range(200):
            key=hashlib.sha256(f'{worker}:{index}'.encode()).hexdigest()
            value={'indexes':['experiences']}
            lifecycle.remember_outcome(key,value)
            found=lifecycle.cached_outcome(key)
            assert found is None or found==value
    with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(exercise,range(8)))
    with lifecycle._OUTCOME_LOCK:
        assert len(lifecycle._OUTCOMES)<=8
        assert all(len(key)==64 for key in lifecycle._OUTCOMES)
