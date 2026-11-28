"""v5.1.12 purge regressions against migrated disposable databases with real FKs."""
import uuid
import pytest
from sqlalchemy import select,inspect
from test_content import client,make_type,record_payload,update_payload,write
from test_api import SessionLocal,engine,csrf,reset_limiter
from test_archive import upload
from test_experiences import card
from test_recovery import deleted,action
from app.content_models import ContentRecord,RecordRevision
from app.experience_models import ArticleOptions,Experience,ExperienceMedia,ActivityExperience
from app.services.experiences import serialize

@pytest.mark.parametrize('structured',[False,True],ids=['plain-options','structured-card'])
def test_purge_removes_options_and_card_children_with_real_restrict_fks(client,structured,monkeypatch):
    t=make_type(client);body=serialize(card()) if structured else '合成普通正文'
    response=write(client,'/records',{**record_payload(t),'body_format':2,'body':body,'article':{'travel_enabled':False,'end_date':None}})
    assert response.status_code==200,response.text
    r=response.json();d=deleted(client,r)
    with SessionLocal() as db:
        assert db.get(ArticleOptions,r['id']) is not None
        assert bool(db.scalar(select(Experience).where(Experience.record_id==r['id'])))==structured
    foreign=inspect(engine).get_foreign_keys('article_options')
    assert any(fk['referred_table']=='content_records' and fk['options'].get('ondelete')=='RESTRICT' for fk in foreign)
    from sqlalchemy.exc import IntegrityError
    from app.routers import recovery as routes
    original=routes.purge;diagnostic={}
    def observed(*args):
        try:return original(*args)
        except IntegrityError as exc:
            diagnostic.update(type='IntegrityError',sqlstate=getattr(exc.orig,'sqlstate',None),constraint=getattr(getattr(exc.orig,'diag',None),'constraint_name',None))
            raise
    monkeypatch.setattr(routes,'purge',observed)
    result=action(client,[d],'purge').json()['items'][0]
    assert result['state']=='purged',{'response':result,'safe_diagnostic':diagnostic}
    with SessionLocal() as db:
        assert db.get(ContentRecord,r['id']) is None
        assert db.get(ArticleOptions,r['id']) is None
        assert db.scalar(select(Experience).where(Experience.record_id==r['id'])) is None

def test_leaf_first_purge_preserves_shared_resources_templates_and_audit(client):
    from test_templates import create,record
    from test_archive import connect
    from app.archive_models import MediaAsset,Place,ResourceReferenceAudit
    from app.life_models import TripActivity,ActivityMedia
    from app.template_models import ContentTemplate,TemplateVersion
    from app.exchange.models import AIInvocation
    from app.models import AdminUser
    from datetime import date
    template=create(client);m=upload(client).json()
    p=client.post('/api/admin/archive/places',headers=csrf(client),json={'name':'合成共享地点'}).json()
    a=card('f',media_ids=[m['id']],fields={'place_id':p['id']});old=card('g',media_ids=[m['id']])
    first=record(client,template,body_format=2,body=serialize(a)+'\n\n'+serialize(old),article={'travel_enabled':True,'end_date':None})
    second=record(client,template,body_format=2,body=serialize(card('m',media_ids=[m['id']])))
    first=connect(client,first,media=[{'id':m['id']}],places=[p['id']]).json()
    # Keep both current and historical source-derived leaves.
    first=write(client,'/records/'+first['id'],update_payload(first,body=serialize(a)),'put').json()
    activity=str(uuid.uuid4());audit=str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(TripActivity(id=activity,record_id=first['id'],day=date(2026,10,18),title='合成活动',position=0,place_id=p['id']))
        db.flush();db.add(ActivityMedia(activity_id=activity,media_id=m['id']))
        db.add(ActivityExperience(activity_id=activity,record_id=first['id'],entry_id=a['id']))
        evidence=db.get(ResourceReferenceAudit,'ig:'+first['id'])
        if evidence:evidence.value={'version':1,'status':'accepted'}
        else:db.add(ResourceReferenceAudit(key='ig:'+first['id'],value={'version':1,'status':'accepted'}))
        db.add(AIInvocation(id=audit,actor_id=db.scalar(select(AdminUser.user_id)),request_key=str(uuid.uuid4()),provider_id=str(uuid.uuid4()),config_revision=1,model='synthetic',action='test',state='succeeded',rules_digest='0'*64))
        db.commit()
    d=deleted(client,first)
    assert action(client,[d],'purge').json()['items'][0]['state']=='purged'
    with SessionLocal() as db:
        for model in [Experience,ExperienceMedia,ActivityExperience,RecordRevision]:
            assert db.scalar(select(model).where(model.record_id==first['id'])) is None
        assert db.get(TripActivity,activity) is None
        assert db.get(ContentRecord,second['id']) is not None
        assert db.get(MediaAsset,m['id']) is not None and db.get(Place,p['id']) is not None
        assert db.get(ContentTemplate,template['id']) is not None and db.get(TemplateVersion,(template['id'],1)) is not None
        assert db.get(ResourceReferenceAudit,'ig:'+first['id']) is not None and db.get(AIInvocation,audit) is not None
    assert client.get('/api/library-media/'+m['id']+'/original').status_code==200
    assert action(client,[d],'purge').json()['items'][0]['state']=='already_purged'

def test_real_fk_failure_rolls_back_one_item_and_commits_next(client,monkeypatch):
    from app.routers import recovery as routes
    t=make_type(client)
    rows=[deleted(client,write(client,'/records',{**record_payload(t),'article':{'travel_enabled':False,'end_date':None}}).json()) for _ in range(2)]
    original=routes.purge
    def fail_first(db,r,expected):
        if r.id==rows[0]['id']:
            db.delete(db.get(ArticleOptions,r.id));db.flush()
            db.add(ArticleOptions(record_id=str(uuid.uuid4()),travel_enabled=False));db.flush() # real FK error
        return original(db,r,expected)
    monkeypatch.setattr(routes,'purge',fail_first)
    result=action(client,rows,'purge').json()['items']
    assert result[0]['state']=='failed' and result[0]['status']==409 and result[0]['code']=='constraint_conflict'
    assert result[1]['state']=='purged'
    assert not any(term in str(result) for term in ['INSERT','article_options','SQLAlchemy','parameters'])
    with SessionLocal() as db:
        assert db.get(ContentRecord,rows[0]['id']) is not None and db.get(ArticleOptions,rows[0]['id']) is not None
        assert db.get(ContentRecord,rows[1]['id']) is None

@pytest.mark.parametrize('error,expected_status,expected_code',[
    ('operational',503,'database_unavailable'),('concurrency',409,'concurrent_update'),
    ('stale',409,'concurrent_update'),('database',500,'database_error'),('unexpected',500,'unexpected_error')])
def test_batch_failure_categories_are_sanitized(client,monkeypatch,error,expected_status,expected_code):
    from app.routers import recovery as routes
    from sqlalchemy.exc import OperationalError,DatabaseError
    from sqlalchemy.orm.exc import StaleDataError
    t=make_type(client);r=deleted(client,write(client,'/records',record_payload(t)).json())
    class DriverFailure(Exception):sqlstate='40001' if error=='concurrency' else None
    secret='synthetic-password-never-echo'
    failures={'operational':OperationalError('SELECT '+secret,{},DriverFailure(secret)),
              'concurrency':OperationalError('SELECT '+secret,{},DriverFailure(secret)),
              'database':DatabaseError('SELECT '+secret,{},DriverFailure(secret)),
              'unexpected':RuntimeError(secret),'stale':StaleDataError(secret)}
    def fail(*args):raise failures[error]
    monkeypatch.setattr(routes,'purge',fail)
    result=action(client,[r],'purge').json()['items'][0]
    assert (result['status'],result['code'])==(expected_status,expected_code)
    assert secret not in str(result) and 'SELECT' not in str(result)
    with SessionLocal() as db:assert db.get(ContentRecord,r['id']) is not None

def test_automatic_cleanup_uses_same_leaf_first_core_and_restores_indexes(client):
    from datetime import timedelta
    from app.services.recovery import cleanup_batch,db_now
    from app.v5_models import FoodOccurrence
    t=make_type(client);e=card('f');r=write(client,'/records',{**record_payload(t),'body_format':2,'body':serialize(e),'article':{'travel_enabled':False,'end_date':None}}).json()
    d=deleted(client,r)
    with SessionLocal() as db:
        assert not db.get(Experience,(r['id'],e['id'])).active
        food=db.scalar(select(FoodOccurrence).where(FoodOccurrence.record_id==r['id']))
        assert not food.active
        food_id=food.id;food.city_override='合成人工城市';food.category='合成人工分类';db.commit()
    restored=action(client,[d],'restore').json()['items'][0];assert restored['state']=='restored'
    current=client.get('/api/admin/content/records/'+r['id']).json()
    changed=write(client,'/records/'+r['id'],update_payload(current,body='当前纯文字'),'put').json()
    response=client.post('/api/admin/recovery/history/'+r['id']+'/1/restore',headers=csrf(client),json={'expected_revision':changed['revision'],'scope':'content','confirmation':'恢复为新草稿'})
    assert response.status_code==200,response.text
    with SessionLocal() as db:
        assert db.get(Experience,(r['id'],e['id'])).active
        food=db.scalar(select(FoodOccurrence).where(FoodOccurrence.record_id==r['id']))
        assert food.active and food.id==food_id
        assert (food.city_override,food.category)==('合成人工城市','合成人工分类')
    d=deleted(client,response.json())
    with SessionLocal() as db:
        row=db.get(ContentRecord,r['id']);row.deleted_at=db_now(db)-timedelta(days=20000);row.created_at=row.deleted_at-timedelta(days=1);db.commit()
        result=cleanup_batch(db,90)
        assert result['removed']>=1 and not any(item['id']==r['id'] for item in result['errors'])
        assert db.get(ContentRecord,r['id']) is None and db.get(ArticleOptions,r['id']) is None

@pytest.mark.parametrize('constraint,state,number,expected',[
    ('article_options_record_id_fkey','23503',787,{'constraint':'article_options_record_id_fkey','sqlstate':'23503','sqlite_code':787}),
    ('synthetic_password_never_log','synthetic-password-never-log',999999,{}),
    ('article_options_record_id_fkey\nsynthetic-password-never-log','23503\nsynthetic-password-never-log',True,{})])
def test_recovery_server_diagnostics_only_log_whitelisted_schema_tokens(caplog,constraint,state,number,expected):
    import logging
    from types import SimpleNamespace
    from sqlalchemy.exc import IntegrityError
    from app.services.recovery import recovery_failure
    secret='synthetic-password-never-log'
    class DriverError(Exception):pass
    orig=DriverError(secret);orig.sqlstate=state;orig.sqlite_errorcode=number;orig.diag=SimpleNamespace(constraint_name=constraint)
    error=IntegrityError('DELETE FROM '+secret,{'password':secret},orig)
    with caplog.at_level(logging.WARNING,logger='app.services.recovery'):
        result=recovery_failure(error)
    assert result['code']=='constraint_conflict'
    records=[record for record in caplog.records if record.name=='app.services.recovery']
    assert len(records)==1
    record=records[0]
    assert record.getMessage()=='recovery_operation_failed' and record.exc_info is None
    assert record.recovery_diagnostic=={'category':'constraint_conflict','exception_type':'IntegrityError',**expected}
    assert secret not in caplog.text and secret not in str(record.recovery_diagnostic)
    assert 'DELETE' not in caplog.text and 'password' not in str(record.recovery_diagnostic)
