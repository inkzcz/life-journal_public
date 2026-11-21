"""Presentation uses synthetic content and the disposable database only."""
import copy
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_content import client,make_type,record_payload,update_payload,write,type_payload
from test_archive import upload,create_record,connect
from test_api import app,login,csrf,SessionLocal,engine,reset_limiter
from app.models import User
from app.security import ph
from app.content_models import ContentRecord,ContentType
from app.blog_models import SiteConfig,Section
A='/api/admin/blog';B='/api/blog'

def put(c,path,data):return c.put(A+path,headers=csrf(c),json=data)
def section(c,types,**kw):
    data={'name':'虚构栏目','slug':'section-'+uuid.uuid4().hex,'type_ids':[t['id'] for t in types],**kw}
    r=c.post(A+'/sections',headers=csrf(c),json=data);assert r.status_code==200,r.text;return r.json()
def section_edit(s,**kw):return {**copy.deepcopy(s),'expected_revision':s['revision'],**kw}
def clean_section(s,**kw):return {k:v for k,v in section_edit(s,**kw).items() if k not in {'id','revision'}}
def module(kind='latest',**kw):return {'id':str(uuid.uuid4()),'kind':kind,**kw}
def config_put(c,key,**kw):
    current=c.get(A+'/'+key).json();current['expected_revision']=current.pop('revision');current.update(kw);return put(c,'/'+key,current)
def reader_client(enabled):
    name='reader-blog-'+uuid.uuid4().hex;password=uuid.uuid4().hex
    with SessionLocal() as db:db.add(User(username=name,password_hash=ph.hash(password)));db.commit()
    c=TestClient(enabled,base_url='https://testserver')
    assert c.post('/api/auth/login',headers=csrf(c),json={'username':name,'password':password}).status_code==200
    return c


def test_sections_many_to_many_stable_links_and_cover_reference(client):
    t1,t2=make_type(client),make_type(client);m=upload(client).json()
    a=section(client,[t1,t2],cover_id=m['id']);b=section(client,[t1])
    one=create_record(client,t1);two=create_record(client,t2)
    page=client.get(B+'/sections/'+a['slug']).json();assert page['total']==2
    assert client.get(B+'/sections/'+b['slug']).json()['total']==1
    r=put(client,'/sections/'+a['id'],clean_section(a,name='重命名栏目'));assert r.status_code==200
    current=r.json();assert current['slug']==a['slug'] and current['id']==a['id']
    assert put(client,'/sections/'+a['id'],clean_section(a)).status_code==409
    assert put(client,'/sections/'+a['id'],clean_section(current,slug='changed')).status_code==422
    assert client.post(A+'/sections',headers=csrf(client),json={'name':'重复','slug':a['slug']}).status_code==409
    assert client.request('DELETE','/api/admin/archive/media/'+m['id'],headers=csrf(client),json={'expected_revision':m['revision']}).status_code==409
    assert client.request('DELETE',A+'/sections/'+a['id'],headers=csrf(client),json={'expected_revision':current['revision']}).status_code==200
    assert client.get(B+'/sections/'+a['slug']).status_code==404
    assert client.get(B+'/records/'+one['id']).status_code==200
    assert client.get(B+'/records/'+two['id']).status_code==200


def test_reader_visibility_drafts_deleted_type_inactive_and_links(client):
    t=make_type(client);published=create_record(client,t);draft=create_record(client,t,status='draft',title='secret draft title');deleted=create_record(client,t,title='secret deleted title')
    published=connect(client,published,links=[{'id':draft['id'],'label':'秘密关系'},{'id':deleted['id'],'label':'旧关系'}]).json()
    assert write(client,'/records/'+deleted['id'],{'expected_revision':deleted['revision']},'delete').status_code==200
    with reader_client(client.app) as reader:
        result=reader.get(B+'/records/'+published['id']);assert result.status_code==200
        assert result.json()['links']==[] and 'secret' not in result.text
        assert reader.get(B+'/records/'+draft['id']).status_code==404
        assert reader.get(B+'/records/'+deleted['id']).status_code==404
        assert reader.get(A+'/preview/'+draft['id']).status_code==403
        assert all(x['id'] not in {draft['id'],deleted['id']} for x in reader.get(B+'/records').json()['items'])
    assert client.get(A+'/preview/'+draft['id']).json()['title']=='secret draft title'
    assert write(client,'/types/'+t['id'],type_payload(t,active=False),'put').status_code==200
    assert client.get(B+'/records/'+published['id']).status_code==404


def test_navigation_targets_depth_cycles_and_private_filter(client):
    t=make_type(client);s=section(client,[t]);draft=create_record(client,t,status='draft')
    root,child,secret=[str(uuid.uuid4()) for _ in range(3)]
    rows=[{'id':root,'name':'栏目根','kind':'section','section_id':s['id']},{'id':child,'name':'日记入口','kind':'page','page':'journals','parent_id':root},{'id':secret,'name':'不能泄露的导航','kind':'record','record_id':draft['id']}]
    r=config_put(client,'navigation',items=rows);assert r.status_code==200,r.text
    result=client.get(B+'/site').json()['navigation'];assert {x['id'] for x in result}=={root,child}
    revision=r.json()['revision'];assert put(client,'/navigation',{'expected_revision':revision-1,'items':[]}).status_code==409
    for invalid in [rows+[{'id':str(uuid.uuid4()),'name':'第三层','kind':'home','parent_id':child}],
                    [{'id':root,'name':'循环','kind':'home','parent_id':root}],
                    [{'id':root,'name':'不存在','kind':'home','parent_id':str(uuid.uuid4())}],
                    [{'id':root,'name':'危险地址','kind':'page','page':'javascript:alert(1)'}]]:
        assert put(client,'/navigation',{'expected_revision':revision,'items':invalid}).status_code==422
    assert client.request('DELETE',A+'/sections/'+s['id'],headers=csrf(client),json={'expected_revision':1}).status_code==200
    assert client.get(B+'/site').json()['navigation']==[]
    assert config_put(client,'navigation',items=[]).status_code==200


def test_layout_all_modules_filter_bad_references_and_safe_config(client):
    t=make_type(client);s=section(client,[t]);pub=create_record(client,t);draft=create_record(client,t,status='draft')
    modules=[module('hero',title='自定义介绍',text='纯文本<script>not executable</script>'),module('text',text='**安全 Markdown**'),module('featured',record_ids=[pub['id'],draft['id']],layout='feature'),module('latest',type_id=t['id']),module('section',section_id=s['id'],layout='grid2'),module('gallery',record_ids=[pub['id']])]
    r=config_put(client,'layout',title='私人生活档案',modules=modules);assert r.status_code==200,r.text
    data=client.get(B+'/home').json();assert len(data['modules'])==6
    assert [x['id'] for x in data['modules'][2]['items']]==[pub['id']]
    assert data['modules'][5]['items']==[]
    assert config_put(client,'layout',modules=[module('latest',css='evil')]).status_code==422
    assert config_put(client,'layout',modules=[module('latest',layout='arbitrary-html')]).status_code==422
    assert config_put(client,'layout',modules=[module('section')]).status_code==422
    assert write(client,'/records/'+pub['id'],{'expected_revision':pub['revision']},'delete').status_code==200
    assert client.get(B+'/home').json()['modules'][2]['items']==[]
    assert client.request('DELETE',A+'/sections/'+s['id'],headers=csrf(client),json={'expected_revision':s['revision']}).status_code==200
    assert all(x['kind']!='section' for x in client.get(B+'/home').json()['modules'])


def test_all_appearances_persist_and_leave_content_and_layout_unchanged(client):
    t=make_type(client);r=create_record(client,t);s=section(client,[t]);layout=client.get(A+'/layout').json()
    before=client.get('/api/admin/content/records/'+r['id']).json()
    for theme in ['modern','editorial','soft','glass']:
        for mode in ['light','dark','system']:
            result=config_put(client,'appearance',theme=theme,mode=mode);assert result.status_code==200,result.text
            assert client.get(B+'/site').json()['appearance']['theme']==theme
    assert client.get(A+'/layout').json()==layout
    assert client.get('/api/admin/content/records/'+r['id']).json()==before
    assert next(x for x in client.get(A+'/sections').json() if x['id']==s['id'])['revision']==s['revision']
    assert config_put(client,'appearance',theme='https://evil.invalid/theme.js').status_code==422
    assert config_put(client,'appearance',css='body{display:none}').status_code==422
    current=client.get(A+'/appearance').json()
    assert put(client,'/appearance',{'expected_revision':current['revision']-1,'theme':'modern','mode':'light'}).status_code==409


def test_permissions_csrf_switch_and_empty_reader(client):
    for path in ['/site','/home','/records','/sections/anything']:
        with TestClient(client.app,base_url='https://testserver') as anon:assert anon.get(B+path).status_code==401
    with reader_client(client.app) as reader:
        assert reader.get(B+'/home').status_code==200
        for path in ['/sections','/appearance','/layout','/navigation']:
            assert reader.get(A+path).status_code==403
            assert reader.request('POST' if path=='/sections' else 'PUT',A+path,headers=csrf(reader),json={}).status_code==403
    with TestClient(app,base_url='https://testserver') as off:
        login(off)
        for path in ['/site','/home','/records']:assert off.get(B+path).status_code==200
        assert off.get(A+'/layout').status_code==200
        assert off.get('/api/journals').status_code==200
    assert client.put(A+'/appearance',json={'theme':'modern','mode':'light','expected_revision':0}).status_code==403


def test_concurrent_configuration_writes_postgresql(client):
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL concurrency')
    current=client.get(A+'/appearance').json();enabled=client.app
    def save(theme):
        with TestClient(enabled,base_url='https://testserver') as other:
            login(other);return put(other,'/appearance',{'expected_revision':current['revision'],'theme':theme,'mode':'light'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(save,['modern','glass']))==[200,409]


def test_reader_pinned_eight_fields_and_exact_decimal(client):
    from test_content import field
    option=str(uuid.uuid4())
    kinds=['short_text','long_text','markdown','integer','decimal','date','select','multiselect']
    specs=[field(kind,position=i,**({'rules':{'options':[{'id':option,'label':'人类可读选择'}]}} if kind in {'select','multiselect'} else {})) for i,kind in enumerate(kinds)]
    t=make_type(client,specs);values=['短文本','长文本','**安全正文**',0,'123456789.123456','2026-10-18',option,[option]]
    ids=[f['id'] for f in t['fields']];payload=record_payload(t,dict(zip(ids,values)));r=write(client,'/records',payload).json()
    updated=type_payload(t);updated['fields'][0]['name']='重命名后的字段';assert write(client,'/types/'+t['id'],updated,'put').status_code==200
    with reader_client(client.app) as reader:
        result=reader.get(B+'/records/'+r['id']).json()
        assert result['schema_version']==1 and result['fields'][0]['name']=='虚构字段'
        assert [f['kind'] for f in result['fields']]==kinds
        assert result['values']==dict(zip(ids,values))
        assert result['fields'][-1]['rules']['options'][0]['label']=='人类可读选择'


def test_reader_dto_does_not_expose_draft_selectors_or_unused_defaults(client):
    from test_content import field
    chosen,hidden=str(uuid.uuid4()),str(uuid.uuid4())
    t=make_type(client,[field('select',has_default=True,default_value=hidden,rules={'options':[{'id':chosen,'label':'可显示选择'},{'id':hidden,'label':'不应随文章泄露的选项'}]})])
    f=t['fields'][0]['id'];pub=write(client,'/records',record_payload(t,{f:chosen})).json();draft=create_record(client,t,status='draft',title='private unpublished selector')
    assert config_put(client,'layout',modules=[module('featured',record_ids=[pub['id'],draft['id']])]).status_code==200
    with reader_client(client.app) as reader:
        response=reader.get(B+'/home');assert draft['id'] not in response.text and 'record_ids' not in response.text
        detail=reader.get(B+'/records/'+pub['id']);assert hidden not in detail.text and 'default_value' not in detail.text
