"""Default article resolution against the disposable test API database only."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select, func
from test_content import client, write, make_type, record_payload, type_payload, update_payload
from test_api import SessionLocal, app, csrf, login, reset_limiter
from app.security import ph
from app.main import create_app
from app.content_models import ContentType, ContentTypeVersion
from app.models import User
from app.services.content import default_article_type
from app.template_models import ContentTemplate, TemplateVersion


def base(client):
    response=write(client,'/types/default-article',{})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['active'] is True and result['fields']==[] and result['version']>=1
    uuid.UUID(result['id'])
    return result


def test_lazy_default_initialization_is_idempotent_and_creates_both_record_modes(client):
    first=base(client)
    for _ in range(3):assert base(client)['id']==first['id']
    for travel in (False,True):
        response=write(client,'/records',record_payload(first,article={'travel_enabled':travel}))
        assert response.status_code==200,response.text
        record=response.json()
        assert record['type_id']==first['id'] and record['article']['travel_enabled'] is travel
        assert record['values']=={} and record['template'] is None
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ContentTypeVersion).where(ContentTypeVersion.type_id==first['id']))==1


def test_customized_and_disabled_defaults_are_preserved_instead_of_reconfigured(client):
    original=base(client)
    configured=type_payload(original,fields=[{'kind':'short_text','name':'保留的高级必填字段','required':True,'position':0}])
    response=write(client,'/types/'+original['id'],configured,'put')
    assert response.status_code==200,response.text
    historical=response.json()
    next_type=base(client)
    assert next_type['id']!=original['id']
    assert client.get('/api/admin/content/types/'+original['id']).json()==historical
    response=write(client,'/types/'+next_type['id'],type_payload(next_type,active=False),'put')
    assert response.status_code==200,response.text
    third=base(client)
    assert third['id'] not in {original['id'],next_type['id']}
    assert client.get('/api/admin/content/types/'+next_type['id']).json()['active'] is False
    assert base(client)['id']==third['id']


def test_parallel_resolvers_reuse_one_identity_and_version(client):
    known=base(client)
    assert write(client,'/types/'+known['id'],type_payload(known,active=False),'put').status_code==200
    with SessionLocal() as db:actor=db.scalar(select(User.id).where(User.username=='test-admin'))
    def resolve(_):
        with SessionLocal() as db:
            value=default_article_type(db,actor);identity=value.id;db.commit();return identity
    with ThreadPoolExecutor(max_workers=4) as pool:
        identities=set(pool.map(resolve,range(8)))
    assert len(identities)==1 and known['id'] not in identities
    assert base(client)['id'] in identities


def test_an_existing_template_binding_is_not_adopted_or_deleted(client):
    original=base(client);identity=str(uuid.uuid4())
    with SessionLocal() as db:
        actor=db.scalar(select(User.id).where(User.username=='test-admin'))
        db.add(ContentTemplate(id=identity,slug='synthetic-'+uuid.uuid4().hex,name='保留的旧模板',
                               type_id=original['id'],active=True,revision=1))
        db.flush()
        db.add(TemplateVersion(template_id=identity,number=1,type_id=original['id'],
            schema_version=original['version'],config={'form':[],'modules':['body']},created_by=actor))
        db.commit()
    assert base(client)['id']!=original['id']
    with SessionLocal() as db:
        assert db.get(ContentTemplate,identity).type_id==original['id']
        assert db.get(TemplateVersion,(identity,1)).schema_version==original['version']


def test_travel_toggle_keeps_dynamic_values_card_identity_and_life_data(client):
    t=make_type(client,[{'kind':'short_text','name':'旧字段','position':0}])
    card={'id':str(uuid.uuid4()),'kind':'m','name':'合成旧电影','fields':{'review':'原评价'},'media_ids':[]}
    body='旧正文\n\n:::lj-entry-v1\n'+json.dumps(card,ensure_ascii=False)+'\n:::\n'
    payload={**record_payload(t,{t['fields'][0]['id']:'历史动态值'}),'body':body,
             'body_format':2,'marker_version':2,'article':{'travel_enabled':True}}
    response=write(client,'/records',payload)
    assert response.status_code==200,response.text
    original=response.json();current=copy.deepcopy(original)
    for enabled in (False,True):
        payload=update_payload(current,body_format=2,marker_version=2,life=current['life'],
                               connections={k:current['connections'][k] for k in ('media','places','links')},
                               article={**current['article'],'travel_enabled':enabled})
        # Connection output carries display details; use this empty synthetic graph.
        payload['connections']={'media':[],'places':[],'links':[]}
        response=write(client,'/records/'+current['id'],payload,'put')
        assert response.status_code==200,response.text
        current=response.json()
        assert current['article']['travel_enabled'] is enabled
        for key in ('id','type_id','body','values','life'):
            assert current[key]==original[key]


def test_default_type_preserves_existing_admin_and_csrf_boundaries(client):
    assert client.post('/api/admin/content/types/default-article',json={}).status_code==403
    disabled=create_app(replace(app.state.settings,dynamic_blog_enabled=False))
    with TestClient(disabled,base_url='https://testserver') as c:
        login(c)
        # The legacy feature flag was already retired in v5.1.9; admin checks
        # remain mandatory even when that historical setting is false.
        assert c.post('/api/admin/content/types/default-article',json={},headers=csrf(c)).status_code==200
    with TestClient(app,base_url='https://testserver') as c:
        assert c.post('/api/admin/content/types/default-article',json={},headers=csrf(c)).status_code==401
    username='synthetic-reader-'+uuid.uuid4().hex
    password=uuid.uuid4().hex
    with SessionLocal() as db:
        db.add(User(username=username,password_hash=ph.hash(password)));db.commit()
    with TestClient(client.app,base_url='https://testserver') as c:
        assert c.post('/api/auth/login',json={'username':username,'password':password},headers=csrf(c)).status_code==200
        assert c.post('/api/admin/content/types/default-article',json={},headers=csrf(c)).status_code==403
