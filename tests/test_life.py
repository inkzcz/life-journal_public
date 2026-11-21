"""Synthetic trips/albums in disposable databases only."""
import copy,uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_api import app,csrf,login,SessionLocal,engine,reset_limiter
from test_content import client,make_type,write,record_payload,update_payload
from test_archive import upload,create_record,connect
from test_blog import reader_client
from app.main import create_app
from app.life_models import TripActivity,ActivityMedia,PhotoAnnotation,TripPlan
from app.content_models import RecordRevision


def sample(client,status='published'):
    t=make_type(client);m=upload(client).json()
    p=client.post('/api/admin/archive/places',headers=csrf(client),json={'name':'虚构地','latitude':'0','longitude':'0'}).json()
    r=create_record(client,t,status=status);r=connect(client,r,media=[{'id':m['id'],'cover':True}],places=[p['id']]).json()
    life={'start_date':'2026-10-18','end_date':'2026-10-20','map_mode':'offline','activities':[{'id':str(uuid.uuid4()),'day':'2026-10-19','time':None,'title':'虚构行程','description':'<script>纯文本</script>','place_id':p['id'],'media_ids':[m['id']]}],'photos':[{'media_id':m['id'],'taken_on':'2026-10-18','place_id':p['id'],'group_name':'第一天'}]}
    return t,m,p,r,life


def put(c,r,life,**kw):return write(c,'/records/'+r['id'],update_payload(r,life=life,**kw),'put')


def test_multiday_edit_order_history_and_soft_deletion(client):
    t,m,p,r,life=sample(client)
    life['activities']+=[{'id':str(uuid.uuid4()),'day':'2026-10-20','time':'12:30','title':'第二天','media_ids':[]},{'id':str(uuid.uuid4()),'day':'2026-10-19','time':'08:00','title':'自定义排序'}]
    response=put(client,r,life);assert response.status_code==200,response.text
    r=response.json();assert [x['title'] for x in r['life']['activities']]==['虚构行程','第二天','自定义排序']
    dto=client.get('/api/blog/records/'+r['id']).json();assert dto['life']==r['life'] and dto['places'][0]['latitude']=='0.000000'
    old=copy.deepcopy(r);life=r['life'];removed=life['activities'].pop(0);life['activities'].reverse();life['map_mode']='hidden'
    response=put(client,r,life);assert response.status_code==200,response.text;r=response.json()
    assert r['life']['map_mode']=='hidden' and r['life']['activities'][0]['title']=='自定义排序'
    with SessionLocal() as db:
        assert db.get(TripActivity,removed['id']).active is False
        assert db.get(ActivityMedia,(removed['id'],m['id'])) is not None
        assert db.get(RecordRevision,(r['id'],old['revision'])).snapshot['life']['activities'][0]['title']=='虚构行程'
    assert write(client,'/records/'+r['id'],{'expected_revision':r['revision']},'delete').status_code==200
    with SessionLocal() as db:assert db.get(TripPlan,r['id']) is not None


def test_validation_refs_and_atomic_rollback(client):
    t,m,p,r,life=sample(client)
    cases=[]
    for key,val in [('end_date','2026-10-17'),('map_mode','https://third-party.example'),('start_date','2026-10-21')]:
        x=copy.deepcopy(life);x[key]=val;cases.append(x)
    for key,val in [('day','2026-11-01'),('day',1700000000),('time','25:00'),('place_id',str(uuid.uuid4())),('media_ids',[str(uuid.uuid4())]),('title',' '),('html','bad')]:
        x=copy.deepcopy(life);x['activities'][0][key]=val;cases.append(x)
    x=copy.deepcopy(life);x['photos'][0]['place_id']=str(uuid.uuid4());cases.append(x)
    x=copy.deepcopy(life);x['photos'][0]['media_id']=str(uuid.uuid4());cases.append(x)
    for x in cases:
        result=put(client,r,x);assert result.status_code==422,result.text
        assert client.get('/api/admin/content/records/'+r['id']).json()['revision']==r['revision']
    with SessionLocal() as db:assert db.get(TripPlan,r['id']) is None
    good=put(client,r,life).json()
    # Cannot remove the record's selected resources while active activities use them.
    assert write(client,'/records/'+good['id'],update_payload(good,connections={'media':[],'links':[],'places':[]}),'put').status_code==422
    assert client.get('/api/admin/content/records/'+good['id']).json()['connections']['media'][0]['id']==m['id']
    other=create_record(client,t)
    other=connect(client,other,media=[{'id':m['id']}],places=[p['id']]).json()
    denied=put(client,other,life);assert denied.status_code==422 and '不属于' in denied.text


def test_draft_incomplete_range_and_permissions(client):
    t,m,p,r,life=sample(client,'draft');life['start_date']=None;life['end_date']=None
    result=put(client,r,life);assert result.status_code==200,result.text;r=result.json()
    assert put(client,r,life,status='published').status_code==422
    assert client.get('/api/blog/records/'+r['id']).status_code==404
    assert client.get('/api/admin/blog/preview/'+r['id']).json()['life']['activities']
    with reader_client(client.app) as c:
        assert c.get('/api/blog/records/'+r['id']).status_code==404
        assert c.put('/api/admin/content/records/'+r['id'],headers=csrf(c),json=update_payload(r,life=life)).status_code==403
        assert c.get('/api/library-media/'+m['id']+'/original').status_code==403
    assert client.put('/api/admin/content/records/'+r['id'],json=update_payload(r,life=life)).status_code==403
    with TestClient(create_app(replace(app.state.settings,dynamic_blog_enabled=False)),base_url='https://testserver') as c:
        login(c);assert c.get('/api/blog/timeline').status_code==200;assert c.get('/api/blog/year-review/2026').status_code==200;assert c.get('/api/journals').status_code==404
    with TestClient(client.app,base_url='https://testserver') as c:
        assert c.get('/api/blog/timeline').status_code==401
        assert c.get('/api/blog/year-review/2026').status_code==401
        assert c.get('/api/library-media/'+m['id']+'/preview').status_code==401


def test_media_history_protection_and_annotation_unlink(client):
    t,m,p,r,life=sample(client);r=put(client,r,life).json()
    life=r['life'];life['activities']=[]
    r=put(client,r,life).json()
    response=write(client,'/records/'+r['id'],update_payload(r,connections={'media':[],'links':[],'places':[p['id']]}),'put');assert response.status_code==200,response.text
    r=response.json();assert r['life']['photos']==[]
    assert client.request('DELETE','/api/admin/archive/media/'+m['id'],headers=csrf(client),json={'expected_revision':m['revision']}).status_code==409
    refs=client.get('/api/admin/archive/media/'+m['id']).json()['references'];assert refs[0]['historical'] is True
    with SessionLocal() as db:assert db.get(PhotoAnnotation,(r['id'],m['id'])).active is False


def test_feed_year_filters_draft_deleted_type_privacy_and_photo_dedup(client):
    t,m,p,r,life=sample(client);r=put(client,r,life,display_date='2025-04-01').json()
    second=create_record(client,t,title='虚构相册',display_date='2025-12-31');second=connect(client,second,media=[{'id':m['id']}],links=[{'id':r['id'],'label':'旅行'}]).json()
    draft=create_record(client,t,title='不能泄露的草稿',display_date='2025-01-01',status='draft')
    second=connect(client,second,media=[{'id':m['id']}],links=[{'id':r['id'],'label':'旅行'},{'id':draft['id'],'label':'秘密'}]).json()
    with reader_client(client.app) as c:
        feed=c.get('/api/blog/timeline',params={'year':2025,'type_id':t['id']}).json()
        assert feed['total']==2 and [x['id'] for x in feed['items']]==[second['id'],r['id']]
        review=c.get('/api/blog/year-review/2025',params={'type_id':t['id']}).json()
        assert review['total']==2 and len(review['photos'])==1 and len(review['photos'][0]['records'])==2
        assert len(review['related'])==1 and '不能泄露' not in str(review)
        assert c.get('/api/blog/timeline?year=0').status_code==422
        assert c.get('/api/blog/year-review/10000').status_code==422
        assert c.get('/api/blog/timeline?type_id=invalid').status_code==422
        assert c.get('/api/blog/timeline?year=2024&type_id='+t['id']).json()['total']==0
    assert write(client,'/records/'+r['id'],{'expected_revision':r['revision']},'delete').status_code==200
    with reader_client(client.app) as c:
        remaining=c.get('/api/blog/year-review/2025?type_id='+t['id']).json();assert remaining['total']==1 and remaining['related']==[]
        assert remaining['photos'][0]['records']==[{'id':second['id'],'title':second['title']}]
    from test_content import type_payload
    assert write(client,'/types/'+t['id'],type_payload(client.get('/api/admin/content/types/'+t['id']).json(),active=False),'put').status_code==200
    with reader_client(client.app) as c:assert c.get('/api/blog/year-review/2025?type_id='+t['id']).json()['total']==0


def test_concurrent_trip_edits(client):
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL concurrency test')
    _,_,_,r,life=sample(client)
    def change(i):
        with TestClient(client.app,base_url='https://testserver') as c:
            login(c);v=copy.deepcopy(life);v['activities'][0]['title']='并发'+str(i);return put(c,r,v).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(change,[1,2]))==[200,409]
