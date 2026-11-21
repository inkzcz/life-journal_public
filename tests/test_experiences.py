"""Synthetic source cards; actual article transactions, media and topic endpoints."""
import json,uuid,copy
import pytest
from test_content import client,make_type,record_payload as base_record_payload,update_payload,write
from test_archive import upload
from test_api import SessionLocal,csrf,reset_limiter
from app.services.experiences import entries,serialize,normalize_quick
from app.experience_models import Experience
from app.content_models import RecordRevision
from fastapi import HTTPException
from sqlalchemy import select

def record_payload(t,**kw):return base_record_payload(t,**({'body_format':2}|kw))

def card(kind='m',name='合成电影',**kw):
    return {'id':str(uuid.uuid4()),'kind':kind,'name':name,'fields':{},'media_ids':[],**kw}

def test_quick_new_markers_normalize_only_on_explicit_save(client):
    t=make_type(client);r=write(client,'/records',{**record_payload(t),'marker_version':2,'body':'@m 合成电影\n\n@s 合成演出\n\n@g 合成礼物'});assert r.status_code==200,r.text
    r=r.json();assert r['body_format']==2
    first=entries(r['body']);assert [e['kind'] for e in first]==['m','s','g']
    r2=write(client,'/records/'+r['id'],update_payload(r),'put').json()
    assert r2['body']==r['body']
    with SessionLocal() as db:assert len(list(db.scalars(select(Experience).where(Experience.record_id==r['id']))))==3

@pytest.mark.parametrize('body',['```\n@m 示例\n```','> @m 引用','    @m 缩进代码','<div>\n@m html\n</div>','@l 合成地\n\n@f 合成店'])
def test_legacy_markers_and_literal_examples_unchanged(body):assert normalize_quick(body)==body

def test_rename_reorder_repeat_and_removal_preserve_ids_and_snapshots(client):
    t=make_type(client);a=card();b=card(name=a['name']);r=write(client,'/records',{**record_payload(t),'body':serialize(a)+'\n\n'+serialize(b)}).json()
    a['name']='新名称';new=serialize(b)+'\n\n'+serialize(a)
    r=write(client,'/records/'+r['id'],update_payload(r,body=new),'put').json()
    for _ in range(2):r=write(client,'/records/'+r['id'],update_payload(r),'put').json()
    with SessionLocal() as db:
        rows=list(db.scalars(select(Experience).where(Experience.record_id==r['id']).order_by(Experience.position)))
        assert [(e.id,e.name) for e in rows]==[(b['id'],b['name']),(a['id'],'新名称')]
    r=write(client,'/records/'+r['id'],update_payload(r,body=serialize(a)),'put').json()
    with SessionLocal() as db:
        assert not db.get(Experience,(r['id'],b['id'])).active
        assert b['id'] in db.get(RecordRevision,(r['id'],1)).snapshot['body']

def test_invalid_and_duplicate_ids_do_not_overwrite_saved_article(client):
    t=make_type(client);e=card();r=write(client,'/records',{**record_payload(t),'body':serialize(e)}).json()
    for source in (':::lj-entry-v1\ninvalid\n:::',serialize({**e,'id':'bad'})):
        result=write(client,'/records/'+r['id'],update_payload(r,body=source),'put');assert result.status_code==422,result.text
        assert client.get('/api/admin/content/records/'+r['id']).json()['body']==r['body']

def test_explicit_food_photos_never_depend_on_indentation_or_neighbor_order(client):
    t=make_type(client);a=upload(client).json();b=upload(client).json()
    f=card('f','甲店',media_ids=[a['id']]);g=card('f','乙店',media_ids=[b['id']])
    r=write(client,'/records',{**record_payload(t),'title':'v519-food-'+uuid.uuid4().hex,'body':serialize(f)+'\n\n'+serialize(g)});assert r.status_code==200,r.text;r=r.json()
    items=client.get('/api/food',params={'q':r['title']}).json()['items'];assert {i['name']:i['cover_id'] for i in items}=={'甲店':a['id'],'乙店':b['id']}
    old={i['name']:i['id'] for i in items}
    f['media_ids']=[b['id'],a['id']]
    result=write(client,'/records/'+r['id'],update_payload(r,body=serialize(g)+'\n\n'+serialize(f)),'put');assert result.status_code==200,result.text
    items=client.get('/api/food',params={'q':r['title']}).json()['items'];assert {i['name']:i['id'] for i in items}==old
    assert next(i for i in items if i['name']=='甲店')['cover_id']==b['id']
    assert client.request('DELETE','/api/admin/archive/media/'+a['id'],headers=csrf(client),json={'expected_revision':a['revision']}).status_code==409


def test_unknown_media_fails_atomically(client):
    t=make_type(client);r=write(client,'/records',{**record_payload(t),'body':serialize(card(media_ids=[str(uuid.uuid4())]))});assert r.status_code==422


def test_topics_hide_drafts_and_deletions_and_allow_repeated_names(client):
    t=make_type(client);e=card('g','同名礼物');a=write(client,'/records',{**record_payload(t),'body':serialize(e)}).json()
    b=write(client,'/records',{**record_payload(t),'status':'draft','body':serialize(e)}).json()
    result=client.get('/api/experiences?kind=g').json()['items'];assert any(x['record_id']==a['id'] for x in result);assert all(x['record_id']!=b['id'] for x in result)
    assert write(client,'/records/'+a['id'],{'expected_revision':a['revision']},'delete').status_code==200
    assert all(x['record_id']!=a['id'] for x in client.get('/api/experiences?kind=g').json()['items'])


def test_transport_cross_day_and_zone_and_missing_fields():
    fields={'transport_type':'飞机','departure':'东京','destination':'洛杉矶','departure_at':'2026-11-14T01:00:00+09:00','arrival_at':'2026-11-13T18:00:00-08:00','departure_zone':'Asia/Tokyo','arrival_zone':'America/Los_Angeles'}
    assert entries(serialize(card('t','SYN123',fields=fields)),published=True)
    for patch in ({'arrival_at':'2026-11-13T01:00:00-08:00'},{'departure_at':'2026-11-14T01:00:00'},{'departure_zone':'America/Los_Angeles'},{'destination':''}):
        with pytest.raises(HTTPException):entries(serialize(card('t','SYN123',fields=fields|patch)),published=True)


def test_reversible_article_mode_keeps_id_body_and_itinerary(client):
    from test_life import sample
    _,_,_,r,life=sample(client)
    r=write(client,'/records/'+r['id'],update_payload(r,life=life,article={'travel_enabled':True,'end_date':'2026-11-30'}),'put').json();assert r['article']['travel_enabled']
    old=copy.deepcopy(r)
    for enabled in (False,True):
        result=write(client,'/records/'+r['id'],update_payload(r,article={'travel_enabled':enabled,'end_date':'2026-11-30'}),'put');assert result.status_code==200,result.text;r=result.json()
        assert r['id']==old['id'] and r['body']==old['body'] and r['life']==old['life'] and r['article']['travel_enabled']==enabled
    result=write(client,'/records/'+r['id'],update_payload(r,article={'travel_enabled':False,'end_date':'1900-01-01'}),'put');assert result.status_code==422


def test_source_copy_assigns_second_identity_once_then_remains_stable(client):
    t=make_type(client);e=card();r=write(client,'/records',{**record_payload(t),'body':serialize(e)+'\n\n'+serialize(e)}).json()
    first=entries(r['body']);assert len({x['id'] for x in first})==2 and first[0]['id']==e['id']
    result=write(client,'/records/'+r['id'],update_payload(r),'put').json();assert result['body']==r['body']


def test_existing_sight_and_transport_shorthand_is_not_reinterpreted_on_save():
    legacy='@s 合成旧景点\n\n@t 合成旧交通地点'
    assert normalize_quick(legacy,legacy)==legacy
    new=normalize_quick(legacy+'\n\n@s 新演出',legacy)
    assert new.startswith(legacy) and len(entries(new))==1


def test_legacy_marker_protocol_survives_rename_and_new_client_payload(client):
    t=make_type(client);r=write(client,'/records',{**record_payload(t),'marker_version':1,'body':'@s 合成旧景点'}).json()
    assert r['marker_version']==1
    result=write(client,'/records/'+r['id'],update_payload(r,marker_version=2,body='@s 已编辑的旧景点'),'put');assert result.status_code==200,result.text
    assert result.json()['body']=='@s 已编辑的旧景点' and result.json()['marker_version']==1
    with SessionLocal() as db:assert not list(db.scalars(select(Experience).where(Experience.record_id==r['id'])))


def test_format_one_code_examples_do_not_activate_literal_media_or_cards(client):
    t=make_type(client);literal=card(media_ids=[str(uuid.uuid4())])
    source='```text\n'+serialize(literal)+'\n```\n\n:::lj-media-v1\n'+json.dumps({'id':str(uuid.uuid4()),'alt':'旧字面块','width':960,'align':'center'})+'\n:::'
    r=write(client,'/records',{**record_payload(t),'body_format':1,'body':source});assert r.status_code==200,r.text
    assert r.json()['body_format']==1 and r.json()['body']==source
    with SessionLocal() as db:assert not list(db.scalars(select(Experience).where(Experience.record_id==r.json()['id'])))


def test_new_quick_marker_cannot_silently_activate_old_literal_resources(client):
    t=make_type(client);source=':::lj-media-v1\n'+json.dumps({'id':str(uuid.uuid4()),'alt':'合成字面示例','width':960,'align':'center'})+'\n:::'
    r=write(client,'/records',{**record_payload(t),'body_format':1,'body':source}).json()
    changed=write(client,'/records/'+r['id'],update_payload(r,body_format=1,body=source+'\n\n@m 新电影'),'put')
    assert changed.status_code==422 and '未自动激活' in changed.text
    assert client.get('/api/admin/content/records/'+r['id']).json()['body']==source
