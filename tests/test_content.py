"""Synthetic dynamic content tests; TEST_DATABASE_URL must be disposable."""
import copy
import uuid
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func, inspect
from test_api import app, login, csrf, reset_limiter, SessionLocal, engine
from app.main import create_app
from app.content_models import ContentRecord, RecordRevision, ContentTypeVersion
from app.models import User
from app.security import ph

PREFIX='/api/admin/content'

@pytest.fixture
def client():
    enabled=create_app(replace(app.state.settings,dynamic_blog_enabled=True))
    with TestClient(enabled,base_url='https://testserver') as c:
        login(c)
        yield c

def write(c,path,data,method='post'):
    return c.request(method.upper(),PREFIX+path,json=data,headers=csrf(c))

def field(kind='short_text',**kw):
    return dict(kind=kind,name='虚构字段',**{'position':0,**kw})

def make_type(c,fields=None):
    data=dict(slug='test-'+uuid.uuid4().hex,name='自定义虚构类型',fields=fields or [])
    r=write(c,'/types',data);assert r.status_code==200,r.text
    return r.json()

def type_payload(t,**changes):
    return {**{k:copy.deepcopy(t[k]) for k in ['slug','name','description','active','fields']},'expected_revision':t['revision'],**changes}

def record_payload(t,values=None,**changes):
    return dict(type_id=t['id'],schema_version=t['revision'],title='虚构记录',body='# 安全正文',display_date='2026-10-18',status='published',values=values or {},**changes)

def update_payload(r,**changes):
    return {**{k:copy.deepcopy(r[k]) for k in ['schema_version','title','body','display_date','status','values']},'expected_revision':r['revision'],**changes}

def test_all_kinds_defaults_validation_and_pagination(client):
    a,b=str(uuid.uuid4()),str(uuid.uuid4())
    specs=[field('short_text',required=True,rules={'min_length':2,'max_length':10}),field('long_text'),field('markdown'),
           field('integer',rules={'min_value':0,'max_value':9}),field('decimal',rules={'min_value':'0','max_value':'100'}),
           field('date',rules={'min_date':'2026-01-01','max_date':'2026-12-31'}),
           field('select',rules={'options':[{'id':a,'label':'选项甲'},{'id':b,'label':'选项乙'}]}),
           field('multiselect',rules={'options':[{'id':a,'label':'选项甲'},{'id':b,'label':'选项乙'}],'max_items':1})]
    values=['示例文本','长文本','**Markdown**',3,'12.3400','2026-10-18',a,[b]]
    for i,f in enumerate(specs):f.update(position=i,has_default=True,default_value=values[i])
    t=make_type(client,specs);ids=[f['id'] for f in t['fields']]
    r=write(client,'/records',record_payload(t));assert r.status_code==200,r.text
    record=r.json();assert record['values']==dict(zip(ids,values))
    invalid=[1,True,1.5,True,12.34,'2026-02-30',str(uuid.uuid4()),[a,b]]
    for fid,bad in zip(ids,invalid):
        assert write(client,'/records',record_payload(t,{fid:bad})).status_code==422
    for value in [False,'NaN','1e3','0.1234567','101']:
        assert write(client,'/records',record_payload(t,{ids[4]:value})).status_code==422
    assert write(client,'/records',record_payload(t,{'unknown':'bad'})).status_code==422
    assert write(client,'/records',{**record_payload(t),'sql':'select 1'}).status_code==422
    page=client.get(PREFIX+'/records',params={'type_id':t['id'],'page_size':1}).json()
    assert page['total']==1 and len(page['items'])==1 and 'values' not in page['items'][0]
    assert client.get(PREFIX+'/records',params={'page':0}).status_code==422
    if engine.dialect.name=='postgresql':
        columns={c['name']:str(c['type']) for c in inspect(engine).get_columns('content_records')}
        assert columns['values']=='JSONB'

def test_version_rename_required_deactivation_and_soft_delete(client):
    t=make_type(client,[field(required=True)])
    fid=t['fields'][0]['id']
    r=write(client,'/records',record_payload(t,{fid:'历史值'})).json()
    changed=type_payload(t);changed['fields'][0]['name']='重新命名';changed['fields'].append(field('integer',required=True,position=1))
    t2=write(client,'/types/'+t['id'],changed,'put').json();assert t2['revision']==2
    old=client.get(PREFIX+'/records/'+r['id']).json()
    assert old['values'][fid]=='历史值' and old['fields'][0]['name']=='虚构字段' and old['schema_version']==1
    assert client.get(PREFIX+f"/types/{t['id']}/versions/1").json()['fields'][0]['id']==fid
    updated=write(client,'/records/'+r['id'],update_payload(r,title='旧版本仍可编辑'),'put');assert updated.status_code==200,updated.text
    r=updated.json()
    assert write(client,'/records/'+r['id'],update_payload(r,schema_version=2),'put').status_code==422
    draft=write(client,'/records/'+r['id'],update_payload(r,schema_version=2,status='draft'),'put');assert draft.status_code==200,draft.text
    r=draft.json();assert r['values'][fid]=='历史值'
    changed=type_payload(t2);changed['fields'][0]['active']=False;changed['active']=False
    t3=write(client,'/types/'+t['id'],changed,'put').json()
    assert write(client,'/records',record_payload(t3)).status_code==409
    # Upgrade retains inactive historical data, but cannot change that value.
    updated=write(client,'/records/'+r['id'],update_payload(r,schema_version=3),'put');assert updated.status_code==200,updated.text
    r=updated.json();assert r['values'][fid]=='历史值'
    assert write(client,'/records/'+r['id'],update_payload(r,values={**r['values'],fid:'覆盖'}),'put').status_code==422
    assert write(client,'/types/'+t['id'],type_payload(t3,fields=t3['fields'][1:]),'put').status_code==422
    assert write(client,'/records/'+r['id'],{'expected_revision':1},'delete').status_code==409
    assert client.request('DELETE',PREFIX+'/records/'+r['id'],json={'expected_revision':r['revision']},headers=csrf(client)).status_code==200
    assert client.get(PREFIX+'/records/'+r['id']).status_code==404
    with SessionLocal() as db:
        kept=db.get(ContentRecord,r['id']);assert kept.deleted_at is not None and kept.values[fid]=='历史值'
        assert db.scalar(select(func.count()).select_from(RecordRevision).where(RecordRevision.record_id==r['id']))==r['revision']+1


def test_type_constraints_and_atomic_failure(client):
    t=make_type(client,[field()])
    assert write(client,'/types',dict(slug=t['slug'],name='重复')).status_code==409
    assert write(client,'/types/'+t['id'],type_payload(t,slug='changed'),'put').status_code==422
    bad=type_payload(t);bad['fields'][0]['kind']='integer'
    assert write(client,'/types/'+t['id'],bad,'put').status_code==422
    bad=type_payload(t);bad['fields'][0]['rules']={'javascript':'alert(1)'}
    assert write(client,'/types/'+t['id'],bad,'put').status_code==422
    assert write(client,'/types/'+t['id'],type_payload(t,fields=[]),'put').status_code==422
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ContentTypeVersion).where(ContentTypeVersion.type_id==t['id']))==1
    assert write(client,'/types/'+t['id'],type_payload(t,name='新名称'),'put').status_code==200
    assert write(client,'/types/'+t['id'],type_payload(t,name='覆盖名称'),'put').status_code==409


def test_choices_stable_ids_and_invalid_definitions(client):
    option=str(uuid.uuid4());t=make_type(client,[field('select',rules={'options':[{'id':option,'label':'原选项'}]})])
    bad=type_payload(t);bad['fields'][0]['rules']['options']=[{'id':str(uuid.uuid4()),'label':'替换'}]
    assert write(client,'/types/'+t['id'],bad,'put').status_code==422
    changed=type_payload(t);changed['fields'][0]['rules']['options'][0]['label']='改名选项'
    new=write(client,'/types/'+t['id'],changed,'put').json()
    assert write(client,'/records',record_payload(new,{new['fields'][0]['id']:option})).status_code==200
    for spec in [field('integer',rules={'min_value':10,'max_value':1}),field('date',rules={'max_length':3}),field('short_text',has_default=True,default_value=42)]:
        assert write(client,'/types',dict(slug='invalid-'+uuid.uuid4().hex,name='无效',fields=[spec])).status_code==422


def test_revision_conflict_actual_parallel_postgresql(client):
    if engine.dialect.name!='postgresql':pytest.skip('requires PostgreSQL concurrent transactions')
    t=make_type(client);r=write(client,'/records',record_payload(t)).json()
    enabled=client.app
    def edit(title):
        with TestClient(enabled,base_url='https://testserver') as other:
            login(other)
            return write(other,'/records/'+r['id'],update_payload(r,title=title),'put').status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(edit,['页面甲','页面乙']))==[200,409]
    current=client.get(PREFIX+'/records/'+r['id']).json();assert current['revision']==2


def test_permission_gate_csrf_and_legacy(client):
    assert client.post(PREFIX+'/types',json={'slug':'csrf','name':'test'}).status_code==403
    with TestClient(client.app,base_url='https://testserver') as anonymous:
        assert anonymous.get(PREFIX+'/types').status_code==401
        assert anonymous.get(PREFIX+'/records').status_code==401
    username='reader-'+uuid.uuid4().hex
    password=uuid.uuid4().hex
    with SessionLocal() as db:
        db.add(User(username=username,password_hash=ph.hash(password)));db.commit()
    with TestClient(client.app,base_url='https://testserver') as reader:
        reader.post('/api/auth/login',headers=csrf(reader),json={'username':username,'password':password})
        assert reader.get(PREFIX+'/types').status_code==403
        assert reader.post(PREFIX+'/types',headers=csrf(reader),json={'slug':'no','name':'no'}).status_code==403
    with TestClient(app,base_url='https://testserver') as disabled:
        login(disabled)
        assert disabled.get(PREFIX+'/types').status_code==200
        assert disabled.get(PREFIX+'/records').status_code==200
        assert disabled.get('/api/journals').status_code==200


def test_database_reference_integrity(client):
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL reference constraints')
    from sqlalchemy.exc import IntegrityError
    from app.content_models import ContentType, FieldDefinition, VersionField
    t=make_type(client,[field()]);other=make_type(client)
    r=write(client,'/records',record_payload(t)).json()
    with SessionLocal() as db:
        # A version cannot reference a stable field belonging to another type.
        db.add(VersionField(type_id=other['id'],version=1,field_id=t['fields'][0]['id'],name='wrong',position=0))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()
        # Type/field/model deletion is rejected by relational references.
        db.delete(db.get(ContentType,t['id']))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()
        db.delete(db.get(FieldDefinition,t['fields'][0]['id']))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()
        assert db.get(ContentRecord,r['id']) is not None


def test_type_parallel_revision_postgresql(client):
    if engine.dialect.name!='postgresql':pytest.skip('requires PostgreSQL concurrent transactions')
    t=make_type(client,[field()]);enabled=client.app
    def configure(name):
        with TestClient(enabled,base_url='https://testserver') as other:
            login(other)
            return write(other,'/types/'+t['id'],type_payload(t,name=name),'put').status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(configure,['名称甲','名称乙']))==[200,409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ContentTypeVersion).where(ContentTypeVersion.type_id==t['id']))==2
