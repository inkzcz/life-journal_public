import uuid
from test_content import client,make_type,record_payload as base_record_payload,write,update_payload
from test_archive import upload
from test_api import csrf,reset_limiter
from app.services.experiences import serialize
from test_experiences import card

def record_payload(t,**kw):return base_record_payload(t,**({'body_format':2}|kw))

def test_cross_article_dedup_body_marker_filters_and_no_draft_leak(client):
    t=make_type(client);a=upload(client).json();private=upload(client).json()
    r=write(client,'/records',{**record_payload(t),'body':serialize(card('m',media_ids=[a['id']]))}).json()
    other=write(client,'/records',{**record_payload(t),'connections':{'media':[{'id':a['id']}]},'display_date':'2026-10-19'}).json()
    draft=write(client,'/records',{**record_payload(t),'status':'draft','body':serialize(card('g',media_ids=[private['id']]))}).json()
    data=client.get('/api/photos',params={'record_id':r['id']});assert data.status_code==200,data.text
    assert [p['id'] for p in data.json()['items']]==[a['id']]
    data=client.get('/api/photos?kind=m').json();p=next(p for p in data['items'] if p['id']==a['id'])
    assert {x['id'] for x in p['records']}=={r['id'],other['id']}
    assert private['id'] not in [p['id'] for p in client.get('/api/photos').json()['items']]
    assert client.get('/api/photos',params={'record_id':draft['id']}).json()['items']==[]
    assert client.get('/api/photos',params={'record_id':r['id'],'year':2025}).json()['items']==[]

def test_multiday_without_photo_date_is_explicitly_uncertain(client):
    t=make_type(client);m=upload(client).json();r=write(client,'/records',{**record_payload(t),'body':serialize(card(media_ids=[m['id']])),'article':{'end_date':'2026-10-20','travel_enabled':False}}).json()
    p=client.get('/api/photos',params={'record_id':r['id']}).json()['items'][0]
    assert p['date'] is None and p['records'][0]['date_source']=='article-range-unknown'
    assert p['records'][0]['range_end']=='2026-10-20'

def test_manual_album_order_cover_conflict_and_media_deletion_protection(client):
    t=make_type(client);a=upload(client).json();b=upload(client).json()
    r=write(client,'/records',{**record_payload(t),'connections':{'media':[{'id':a['id']},{'id':b['id']}]}}).json()
    create={'name':'合成相册','media_ids':[b['id'],a['id']],'cover_id':b['id'],'expected_revision':0}
    res=client.post('/api/admin/photo-albums',headers=csrf(client),json=create);assert res.status_code==200,res.text;album=res.json()
    items=client.get('/api/photos',params={'album_id':album['id']}).json()['items'];assert [p['id'] for p in items]==[b['id'],a['id']]
    albums=client.get('/api/photos/albums');assert albums.status_code==200,albums.text
    assert next(x for x in albums.json() if x['id']==album['id'])['cover_id']==b['id']
    assert client.put('/api/admin/photo-albums/'+album['id'],headers=csrf(client),json=create).status_code==409
    unused=upload(client).json();res=client.put('/api/admin/photo-albums/'+album['id'],headers=csrf(client),json={**create,'media_ids':[unused['id']],'cover_id':unused['id'],'expected_revision':1});assert res.status_code==200,res.text
    assert client.request('DELETE','/api/admin/archive/media/'+unused['id'],headers=csrf(client),json={'expected_revision':unused['revision']}).status_code==409
    assert next(x for x in client.get('/api/photos/albums').json() if x['id']==album['id'])['cover_id'] is None
    assert client.delete('/api/admin/photo-albums/'+album['id'],params={'expected_revision':2},headers=csrf(client)).status_code==200
    assert client.get('/api/admin/archive/media/'+unused['id']).status_code==200


def test_explicit_card_place_filters_photos_without_guessing_article_proximity(client):
    t=make_type(client);m=upload(client).json();unscoped=upload(client).json()
    p=client.post('/api/admin/archive/places',headers=csrf(client),json={'name':'合成相册地点'}).json()
    e=card('f','明确配图店',fields={'place_id':p['id']},media_ids=[m['id']])
    r=write(client,'/records',{**record_payload(t),'body':serialize(e),'connections':{'media':[{'id':unscoped['id']}]}}).json()
    data=client.get('/api/photos',params={'record_id':r['id'],'place_id':p['id']});assert data.status_code==200,data.text
    assert [x['id'] for x in data.json()['items']]==[m['id']]
