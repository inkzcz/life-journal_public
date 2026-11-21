"""Publication and reconciliation use disposable data and existing write gates."""
import uuid
from test_content import client,make_type,record_payload,update_payload,write
from test_api import csrf,SessionLocal
from app.life_models import TripActivity
from app.archive_models import ResourceReferenceAudit

BODY='## 2026-10-03\n\n- @l[合成地区] @f[合成餐厅]\n  - 午饭很开心。'

def test_draft_is_inert_first_publication_generates_and_repeat_publication_preserves_manual_edit(client):
    t=make_type(client)
    response=write(client,'/records',{**record_payload(t), 'body':BODY,'status':'draft','life':{'start_date':'2026-10-03'}})
    assert response.status_code==200,response.text
    r=response.json();assert not r['life']['activities'];assert r['itinerary_generation']['status']=='not_generated'
    published=write(client,'/records/'+r['id'],update_payload(r,status='published'),'put')
    assert published.status_code==200,published.text
    r=published.json();assert r['status']=='published';assert len(r['life']['activities'])==1,r
    assert r['life']['activities'][0]['place_id'];assert r['itinerary_generation']['status']=='needs_review'
    with SessionLocal() as db:assert db.get(TripActivity,r['life']['activities'][0]['id']).markdown_owned
    life=r['life'];life['activities'][0]['description']='人工维护，不得覆盖'
    changed=write(client,'/records/'+r['id'],update_payload(r,body=BODY+'\n\n- @s[合成新景点]',life=life),'put')
    assert changed.status_code==200,changed.text
    r=changed.json();assert len(r['life']['activities'])==1
    assert r['life']['activities'][0]['description']=='人工维护，不得覆盖'
    assert r['itinerary_generation']['status']=='body_updated'
    with SessionLocal() as db:assert not db.get(TripActivity,r['life']['activities'][0]['id']).markdown_owned
    preview=client.post('/api/admin/content/records/'+r['id']+'/itinerary-sync-preview',headers=csrf(client),json={'expected_revision':r['revision'],'body':r['body']})
    assert preview.status_code==200,preview.text
    p=preview.json();assert len(p['preserved'])==1 and len(p['changes'])==1
    assert len(p['conflicts'])==1 and p['conflicts'][0]['id']==r['life']['activities'][0]['id']
    applied=client.post('/api/admin/content/records/'+r['id']+'/itinerary-sync-confirm',headers=csrf(client),json={'expected_revision':r['revision'],'body_hash':p['body_hash']})
    assert applied.status_code==200,applied.text
    assert len(applied.json()['life']['activities'])==2
    assert applied.json()['life']['activities'][0]['description']=='人工维护，不得覆盖'
    stale=client.post('/api/admin/content/records/'+r['id']+'/itinerary-sync-confirm',headers=csrf(client),json={'expected_revision':r['revision'],'body_hash':p['body_hash']})
    assert stale.status_code==409


def test_failed_extraction_does_not_undo_article_publication_and_is_durable(client,monkeypatch):
    import app.services.itinerary_generation as generation
    t=make_type(client)
    r=write(client,'/records',{**record_payload(t),'body':BODY,'status':'draft','life':{'start_date':'2026-10-03'}}).json()
    monkeypatch.setattr(generation,'proposal',lambda *_:(_ for _ in ()).throw(RuntimeError('synthetic failure')))
    response=write(client,'/records/'+r['id'],update_payload(r,status='published'),'put')
    assert response.status_code==200,response.text
    saved=client.get('/api/admin/content/records/'+r['id']).json()
    assert saved['status']=='published' and saved['body']==BODY and not saved['life']['activities']
    assert saved['itinerary_generation']['status']=='failed'
    with SessionLocal() as db:assert db.get(ResourceReferenceAudit,'ig:'+r['id']).value['status']=='failed'


def test_ordinary_article_does_not_generate_itinerary(client):
    t=make_type(client)
    r=write(client,'/records',{**record_payload(t),'body':BODY,'status':'published'}).json()
    assert not r['life']['activities'] and r['itinerary_generation']['status']=='not_generated'


def test_nested_media_metadata_is_not_inferred_as_places_or_activity_text():
    import json
    from app.services.markdown_marks import parse
    from app.services.itinerary import extract
    from datetime import date
    media=':::lj-media-v1\n'+json.dumps({'id':str(uuid.uuid4()),'alt':'@f不能作为餐厅','caption':'@l不能作为地区'})+'\n:::'
    body=BODY+'\n\n'+'\n'.join('  '+line for line in media.splitlines())
    assert all('不能作为' not in mark['name'] for mark in parse(body).marks)
    result=extract(body,date(2026,10,3))
    assert len(result['items'])==1
    assert ':::lj-media' not in result['items'][0]['description']
    assert '不能作为' not in result['items'][0]['description']


def test_confirmed_diff_updates_generated_description_and_preserves_manual_media_and_order(client):
    from test_archive import upload
    from test_markdown_travel import reconcile
    t=make_type(client);m=upload(client).json()
    body=BODY+'\n\n- @s[合成景点]\n  - 阳光很好。'
    r=write(client,'/records',{**record_payload(t),'body':body,'life':{'start_date':'2026-10-03'},'connections':{'media':[{'id':m['id']}]}}).json()
    assert len(r['life']['activities'])==2
    first_id=r['life']['activities'][0]['id']
    changed=write(client,'/records/'+r['id'],update_payload(r,body=body.replace('午饭很开心。','午饭描述已更新。'),life=r['life']),'put').json()
    assert changed['life']['activities'][0]['description']=='午饭很开心。'
    r=reconcile(client,changed)
    assert r['life']['activities'][0]['id']==first_id
    assert r['life']['activities'][0]['description']=='午饭描述已更新。'
    life=r['life'];life['activities'][0]['media_ids']=[m['id']];life['activities'].reverse()
    changed=write(client,'/records/'+r['id'],update_payload(r,life=life),'put')
    assert changed.status_code==200,changed.text
    r=changed.json()
    with SessionLocal() as db:assert all(not db.get(TripActivity,a['id']).markdown_owned for a in r['life']['activities'])
    preserved=reconcile(client,r)
    assert [a['id'] for a in preserved['life']['activities']]==[a['id'] for a in r['life']['activities']]
    assert next(a for a in preserved['life']['activities'] if a['id']==first_id)['media_ids']==[m['id']]


def test_explicit_nested_media_is_associated_with_its_activity_only(client):
    from test_archive import upload
    from test_writing import block
    t=make_type(client);m=upload(client).json()
    body=BODY+'\n\n'+'\n'.join('  '+line for line in block(m['id']).splitlines())+'\n\n- @s[下一站]\n  - 没有照片。'
    result=write(client,'/records',{**record_payload(t),'body':body,'body_format':2,'life':{'start_date':'2026-10-03'}})
    assert result.status_code==200,result.text
    activities=result.json()['life']['activities']
    assert len(activities)==2
    assert activities[0]['media_ids']==[m['id']]
    assert activities[1]['media_ids']==[]


def test_ordinary_photo_metadata_does_not_turn_an_article_into_a_trip(client):
    from test_archive import upload
    m=upload(client).json();t=make_type(client)
    result=write(client,'/records',{**record_payload(t),'body':BODY,'connections':{'media':[{'id':m['id']}]},'life':{'photos':[{'media_id':m['id'],'taken_on':'2026-10-03'}]}})
    assert result.status_code==200,result.text
    r=result.json();assert r['revision']==1 and not r['life']['activities']
    assert r['itinerary_generation']['status']=='not_generated'
    with SessionLocal() as db:assert db.get(ResourceReferenceAudit,'ig:'+r['id']) is None


def test_travel_template_without_start_date_reports_failed_extraction_after_publication(client):
    from test_content import field
    t=make_type(client,[{**field('date'),'name':'出发日期'}])
    result=write(client,'/records',{**record_payload(t),'body':BODY})
    assert result.status_code==200,result.text
    r=result.json();assert r['status']=='published' and not r['life']['activities']
    assert r['itinerary_generation']['status']=='failed'


def test_compact_mark_does_not_silently_truncate_at_an_inline_code_barrier():
    import pytest
    from fastapi import HTTPException
    from app.services.markdown_marks import parse
    with pytest.raises(HTTPException) as caught:parse('@f餐`厅`')
    assert caught.value.status_code==422
    assert parse('@f[餐厅] `备注代码`').marks[0]['name']=='餐厅'


def test_partial_life_update_preserves_existing_itinerary_and_photos(client):
    from test_archive import upload
    t=make_type(client);m=upload(client).json()
    r=write(client,'/records',{**record_payload(t),'body':BODY,'connections':{'media':[{'id':m['id']}]},'life':{'start_date':'2026-10-03','photos':[{'media_id':m['id'],'taken_on':'2026-10-03'}]}}).json()
    original=r['life']
    changed=write(client,'/records/'+r['id'],update_payload(r,body=BODY+'\n\n补充一段记忆。',life={'start_date':'2026-10-03'}),'put')
    assert changed.status_code==200,changed.text
    assert changed.json()['life']['activities']==original['activities']
    assert changed.json()['life']['photos']==original['photos']


def test_publication_extracts_explicit_activities_without_turning_story_tables_into_an_itinerary(client):
    t=make_type(client)
    body=BODY+'\n\n- @h[合成旅店]\n  - 停车方便。\n\n## 第2天\n\n- @s[合成景点]\n  - 上午游览。\n\n|项目|记录|\n|---|---|\n|中文表格|必须原样保留|\n\n开篇。\n\n## 旅途记忆\n\n连续中文输入，页面稳定。'
    result=write(client,'/records',{**record_payload(t),'body':body,'life':{'start_date':'2026-10-03'}})
    assert result.status_code==200,result.text
    r=result.json();assert r['body']==body and len(r['life']['activities'])==3
    assert all('中文表格' not in a['title'] and '开篇' not in a['title'] and '旅途记忆' not in a['title'] for a in r['life']['activities'])


def test_long_story_paragraphs_do_not_consume_the_structured_activity_limit(client):
    t=make_type(client)
    body='## 2026-10-03\n\n'+'\n\n'.join('这是自由叙述的第'+str(i)+'段记忆，不是活动标题。' for i in range(350))+'\n\n- @f[最后的合成晚餐]\n  - 不应因前面的叙述被忽略。'
    response=write(client,'/records',{**record_payload(t),'body':body,'life':{'start_date':'2026-10-03'}})
    assert response.status_code==200,response.text
    r=response.json();assert r['body']==body and len(r['life']['activities'])==1
    assert '最后的合成晚餐' in r['life']['activities'][0]['title']
