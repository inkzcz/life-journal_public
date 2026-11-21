"""Disposable data only: templates reuse schema validation, history and archive locks."""
import copy
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient
from test_content import client, write, update_payload, field, make_type, record_payload
from test_api import csrf, SessionLocal, app, login, engine, reset_limiter
from app.template_models import TemplateVersion, RecordTemplate
from app.content_models import RecordRevision, ContentTypeVersion
from app.blog_models import SiteConfig, Section, NavigationItem
from app.main import create_app
from dataclasses import replace

P='/api/admin/templates'

def save(c,data,id=None):
    return c.request('PUT' if id else 'POST',P+('/'+id if id else ''),json=data,headers=csrf(c))

def edit(t,**changes):
    return {**{k:copy.deepcopy(t[k]) for k in ['slug','name','description','active','fields','modules','expected_type_revision']},'expected_revision':t['revision'],**changes}

def create(c,preset=0):
    source=c.get(P+'/presets').json()[preset];source.pop('key')
    r=save(c,source);assert r.status_code==200,r.text
    return r.json()

def record(c,t,**kw):
    values={f['key']:('2026-10-18' if f['field']['kind']=='date' else '虚构值') for f in t['fields'] if f['field']['active']}
    data=dict(type_id=t['type_id'],schema_version=t['schema_version'],title='虚构模板文章',body='## 私人故事',display_date='2026-10-18',status='published',values=values,template={'id':t['id'],'version':t['version']})
    data.update(kw);r=write(c,'/records',data);assert r.status_code==200,r.text
    return r.json()

@pytest.mark.parametrize('index',range(4))
def test_starters_publish_render_and_edit(client,index):
    t=create(client,index);r=record(client,t)
    assert r['template']['version']==1
    detail=client.get('/api/blog/records/'+r['id']);assert detail.status_code==200
    assert detail.json()['template']['config']['modules']==t['modules']
    assert detail.json()['values']==r['values']
    changed=write(client,'/records/'+r['id'],update_payload(r,title='编辑后标题'),'put')
    assert changed.status_code==200,changed.text
    assert changed.json()['template']['version']==1
    with SessionLocal() as db:
        history=db.get(RecordRevision,(r['id'],2)).snapshot
        assert history['template']['version']==1
        assert history['values']==r['values']


def test_versions_removal_required_upgrade_copy_and_disable(client):
    t=create(client);r=record(client,t);fid=t['fields'][0]['key']
    data=edit(t);data['fields'][0]['field'].update(name='新的显示名称',active=False)
    data['fields'][0]['group']='新的组名'
    data['fields'].append({'key':str(uuid.uuid4()),'group':'补充信息','field':field('integer',required=True,position=len(data['fields']))})
    data['modules'].reverse()
    response=save(client,data,t['id']);assert response.status_code==200,response.text
    t2=response.json();newid=t2['fields'][-1]['key']
    old=client.get('/api/blog/records/'+r['id']).json()
    assert old['template']['version']==1 and old['fields'][0]['name']=='目的地' and old['values'][fid]=='虚构值'
    # Old published record can still be edited against its pinned model.
    response=write(client,'/records/'+r['id'],update_payload(r,title='旧版本继续可编辑'),'put');assert response.status_code==200,response.text
    r=response.json()
    payload=update_payload(r,schema_version=t2['schema_version'],template={'id':t2['id'],'version':2})
    assert write(client,'/records/'+r['id'],payload,'put').status_code==422
    payload['values'][newid]=7
    response=write(client,'/records/'+r['id'],payload,'put');assert response.status_code==200,response.text
    r=response.json();assert r['values'][fid]=='虚构值' and r['template']['version']==2
    assert client.get('/api/blog/records/'+r['id']).json()['values'][fid]=='虚构值'
    assert save(client,edit(t2,fields=t2['fields'][1:]),t2['id']).status_code==422
    copied=client.post(P+'/'+t2['id']+'/copy',json={'slug':'copy-'+uuid.uuid4().hex,'name':'模板副本','expected_revision':2},headers=csrf(client))
    assert copied.status_code==200,copied.text
    cp=copied.json();assert cp['type_id']!=t2['type_id']
    assert set(f['key'] for f in cp['fields']).isdisjoint(f['key'] for f in t2['fields'])
    assert all(str(x) in {f['key'] for f in cp['fields']} for m in cp['modules'] for x in m['field_ids'])
    t3=save(client,edit(t2,active=False),t2['id']).json()
    assert client.get('/api/blog/records/'+r['id']).status_code==200
    assert write(client,'/records',dict(type_id=t3['type_id'],schema_version=t3['schema_version'],title='禁止',body='',display_date='2026-10-18',status='draft',values={},template={'id':t3['id'],'version':3})).status_code==409
    assert write(client,'/records/'+r['id'],update_payload(r,title='停用模板旧记录仍可编辑'),'put').status_code==200
    reset=client.get(P+'/'+t['id']+'/defaults').json()
    assert reset['fields'][0]['field']['name']=='目的地'
    assert reset['fields'][-1]['field']['active'] is False
    assert save(client,edit(reset),t['id']).status_code==200
    with SessionLocal() as db:
        assert db.get(TemplateVersion,(t['id'],1)) is not None
        assert db.get(RecordTemplate,r['id']).version==2


def test_configuration_whitelist_and_atomicity(client):
    t=create(client)
    duplicate=edit(t);duplicate.pop('expected_revision');duplicate['fields']=[];duplicate['modules']=[]
    assert save(client,duplicate).status_code==409
    assert client.post(P+'/'+t['id']+'/copy',json={'slug':t['slug'],'name':'重复标识','expected_revision':1},headers=csrf(client)).status_code==409
    cases=[]
    x=edit(t);x['javascript']='alert(1)';cases.append(x)
    x=edit(t);x['modules'][0]['html']='<script>';cases.append(x)
    x=edit(t);x['modules'][0]['layout']='position:fixed';cases.append(x)
    x=edit(t);x['modules'][1]['field_ids']=[str(uuid.uuid4())];cases.append(x)
    x=edit(t);x['modules'][-2]['kind']='timeline';x['modules'][-2]['field_ids']=[t['fields'][0]['key']];cases.append(x)
    x=edit(t);x['fields'][0]['field']['kind']='date';cases.append(x)
    for data in cases:assert save(client,data,t['id']).status_code==422
    assert client.get(P+'/'+t['id']).json()['revision']==1
    with SessionLocal() as db:
        assert len(list(db.scalars(select(TemplateVersion).where(TemplateVersion.template_id==t['id']))))==1
        assert len(list(db.scalars(select(ContentTypeVersion).where(ContentTypeVersion.type_id==t['type_id']))))==1
    r=record(client,t)
    assert write(client,'/records/'+r['id'],update_payload(r,template={'id':str(uuid.uuid4()),'version':1}),'put').status_code==404
    assert client.get('/api/admin/content/records/'+r['id']).json()['revision']==1
    # Bound type cannot be bypassed through the ordinary create-record endpoint.
    assert write(client,'/records',dict(type_id=t['type_id'],schema_version=1,title='绕过',body='',display_date='2026-10-18',status='draft',values={})).status_code==409


def test_conflicts_and_site_config_unchanged(client):
    t=create(client)
    with SessionLocal() as db:
        before=[[(x.id,copy.deepcopy(x.__dict__.get('value'))) for x in db.scalars(select(model))] for model in [SiteConfig,Section,NavigationItem]]
    a=save(client,edit(t,name='已保存的新名称'),t['id']);assert a.status_code==200
    assert save(client,edit(t,name='过期修改'),t['id']).status_code==409
    assert client.post(P+'/'+t['id']+'/copy',json={'slug':'copy-'+uuid.uuid4().hex,'name':'副本','expected_revision':1},headers=csrf(client)).status_code==409
    # Out-of-band type edit is detected, never overwritten by a stale template editor.
    t=a.json();ct=client.get('/api/admin/content/types/'+t['type_id']).json()
    from test_content import type_payload
    assert write(client,'/types/'+ct['id'],type_payload(ct,name='直接改类型'),'put').status_code==200
    assert save(client,edit(t),t['id']).status_code==409
    with SessionLocal() as db:
        after=[[(x.id,copy.deepcopy(x.__dict__.get('value'))) for x in db.scalars(select(model))] for model in [SiteConfig,Section,NavigationItem]]
    assert before==after


def test_permission_flag_csrf_and_draft(client):
    t=create(client);r=record(client,t,status='draft')
    assert client.get('/api/blog/records/'+r['id']).status_code==404
    assert client.get('/api/admin/blog/preview/'+r['id']).status_code==200
    assert client.post(P,json={}).status_code==403
    disabled=create_app(replace(app.state.settings,dynamic_blog_enabled=False))
    with TestClient(disabled,base_url='https://testserver') as c:
        login(c);assert c.get(P).status_code==200
        assert c.get(P+'/presets').status_code==200
        assert c.get('/api/journals').status_code==404
    enabled=create_app(replace(app.state.settings,dynamic_blog_enabled=True))
    with TestClient(enabled,base_url='https://testserver') as c:
        assert c.get(P).status_code==401
        from test_blog import reader_client
        with reader_client(enabled) as reader:
            assert reader.get(P).status_code==403
            assert reader.get('/api/admin/blog/preview/'+r['id']).status_code==403
            assert reader.get('/api/blog/records/'+r['id']).status_code==404


def test_postgres_concurrent_template_updates(client):
    if engine.dialect.name!='postgresql':pytest.skip('requires PostgreSQL lock test')
    t=create(client);payload=edit(t)
    def change(n):
        with TestClient(create_app(replace(app.state.settings,dynamic_blog_enabled=True)),base_url='https://testserver') as c:
            login(c);return save(c,{**payload,'name':'并发'+str(n)},t['id']).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(change,[1,2]))
    assert sorted(results)==[200,409]
    with SessionLocal() as db:assert len(list(db.scalars(select(TemplateVersion).where(TemplateVersion.template_id==t['id']))))==2
