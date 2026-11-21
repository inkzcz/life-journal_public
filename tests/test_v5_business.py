"""Synthetic v5 integration tests reuse the original auth/CSRF and content API."""
import uuid
import pytest
from sqlalchemy import update
from sqlalchemy import select
from test_content import client,make_type,record_payload,write,update_payload
from test_api import csrf,SessionLocal,reset_limiter
from test_archive import upload
from app.v5_models import FoodOccurrence,RecordMediaFolder,MediaArchiveRule
from app.archive_models import MediaAsset
A='/api/admin/organization'
@pytest.fixture(autouse=True)
def isolated_rules():
    with SessionLocal() as db:db.execute(update(MediaArchiveRule).values(enabled=False));db.commit()
    yield
    with SessionLocal() as db:db.execute(update(MediaArchiveRule).values(enabled=False));db.commit()
def payload(t,**changes):
    p=record_payload(t);p.update(changes);return p
def test_archive_preview_transaction_revision_and_replay(client):
    a=upload(client).json();b=upload(client).json()
    rule=client.post(A+'/rules',headers=csrf(client),json={'name':'拍摄月','date_source':'captured','fallback':'unknown','enabled':True,'by_type':True}).json()
    plan=client.post(A+'/rules/'+rule['id']+'/preview',headers=csrf(client),json={'items':[{'id':x['id'],'expected_revision':x['revision']} for x in [a,b]]})
    assert plan.status_code==200,plan.text
    assert plan.json()['items'][0]['path']==['拍摄日期未知','JPEG']
    result=client.post(A+'/plans/'+plan.json()['id']+'/execute',headers=csrf(client),json={'confirmation':'确认逻辑归档'})
    assert result.status_code==200,result.text
    again=client.post(A+'/plans/'+plan.json()['id']+'/execute',headers=csrf(client),json={'confirmation':'确认逻辑归档'})
    assert again.json()['replayed'] is True
    with SessionLocal() as db:
        assert db.get(MediaAsset,a['id']).sha256==a['sha256']
        assert db.get(MediaAsset,a['id']).folder_id==db.get(MediaAsset,b['id']).folder_id

def test_rule_default_off_and_upload_does_not_silently_move_existing_media(client):
    rule=client.post(A+'/rules',headers=csrf(client),json={'name':'上传年'}).json();assert not rule['enabled']
    a=upload(client).json();assert a['folder_id'] is None
    plan=client.post(A+'/rules/'+rule['id']+'/preview',headers=csrf(client),json={'items':[{'id':a['id'],'expected_revision':a['revision']}]}).json()
    assert client.post(A+'/plans/'+plan['id']+'/execute',headers=csrf(client),json={'confirmation':'确认逻辑归档'}).status_code==409
    rule=client.put(A+'/rules/'+rule['id'],headers=csrf(client),json={**{k:v for k,v in rule.items() if k not in ['id','revision']},'expected_revision':rule['revision'],'enabled':True}).json()
    b=upload(client).json();assert b['folder_id']
    assert client.get('/api/admin/archive/media/'+a['id']).json()['folder_id'] is None

def test_article_folder_stable_and_failed_save_rolls_back(client):
    t=make_type(client);r=write(client,'/records',payload(t,status='draft')).json();folder=r['media_folder_id'];assert folder
    updated=write(client,'/records/'+r['id'],update_payload(r,title='新的名字'),'put').json();assert updated['media_folder_id']==folder
    assert write(client,'/records/'+r['id'],update_payload(r,title='陈旧覆盖'),'put').status_code==409
    with SessionLocal() as db:assert len(list(db.scalars(select(RecordMediaFolder).where(RecordMediaFolder.record_id==r['id']))))==1

def test_food_nested_descriptions_repeated_meals_drafts_and_city_override(client):
    t=make_type(client);body='@l 成都\n\n- @f 小饭馆\n  - 好吃\n  - 两个人吃了160元\n\n- @f 小饭馆\n'
    r=write(client,'/records',payload(t,body=body,status='draft',title='v5-food-'+uuid.uuid4().hex));assert r.status_code==200,r.text;r=r.json();url='/api/food?q='+r['title']
    assert client.get(url).json()['total']==0
    r=write(client,'/records/'+r['id'],update_payload(r,status='published'),'put').json()
    items=client.get(url).json()['items'];assert len(items)==2
    assert any('160元' in x['description'] for x in items)
    assert all(x['city']=='成都' for x in items)
    item=next(x for x in items if '160元' in x['description'])
    assert client.put('/api/admin/food/occurrences/'+item['id'],headers=csrf(client),json={'expected_revision':item['revision'],'city_override':'成都高新区','category':'川菜'}).status_code==200
    for _ in range(2):assert client.post('/api/admin/food/rebuild',headers=csrf(client)).status_code==200
    result=client.get('/api/food?city=成都高新区').json();assert result['total']==1
    assert result['items'][0]['id']==item['id']
    assert client.request('DELETE','/api/admin/content/records/'+r['id'],headers=csrf(client),json={'expected_revision':r['revision']}).status_code==200
    assert client.get(url).json()['total']==0

def test_per_item_media_actions_report_blocked_without_deleting_other_files(client):
    a=upload(client).json();b=upload(client).json()
    result=client.post(A+'/media-actions',headers=csrf(client),json={'confirmation':'逐项处理图片','action':'trash','items':[{'id':a['id'],'expected_revision':a['revision']},{'id':b['id'],'expected_revision':99}]})
    assert result.status_code==200,result.text
    assert [x['state'] for x in result.json()['items']]==['completed','blocked']
    assert client.get('/api/admin/archive/media/'+b['id']).status_code==200

def test_archive_stale_plan_is_atomic_and_rule_change_invalidates(client):
    a=upload(client).json();b=upload(client).json()
    rule=client.post(A+'/rules',headers=csrf(client),json={'name':'并发归档','enabled':True}).json()
    def preview():return client.post(A+'/rules/'+rule['id']+'/preview',headers=csrf(client),json={'items':[{'id':x['id'],'expected_revision':x['revision']} for x in [a,b]]}).json()
    p=preview()
    # Another operation modifies one member: no other member may be moved.
    client.post(A+'/media-actions',headers=csrf(client),json={'confirmation':'逐项处理图片','action':'unfile','items':[{'id':b['id'],'expected_revision':b['revision']}]})
    result=client.post(A+'/plans/'+p['id']+'/execute',headers=csrf(client),json={'confirmation':'确认逻辑归档'})
    assert result.status_code==409
    assert client.get('/api/admin/archive/media/'+a['id']).json()['folder_id']==a['folder_id']
    with SessionLocal() as db:
        from app.v5_models import MediaArchivePlan
        assert not db.get(MediaArchivePlan,p['id']).completed

def test_global_tag_delete_keeps_article_and_blocks_stale_resurrection(client):
    name='已删除标签-'+uuid.uuid4().hex
    tag=client.post('/api/admin/tags',headers=csrf(client),json={'name':name}).json()
    t=make_type(client);r=write(client,'/records',payload(t,tag_ids=[tag['id']])).json()
    usage=client.get('/api/admin/tags/'+tag['id']+'/usage').json();assert usage['count']==1
    result=client.post('/api/admin/tags/'+tag['id']+'/delete-everywhere',headers=csrf(client),json={'name':name,'confirmation_token':usage['confirmation_token']})
    assert result.status_code==200,result.text
    kept=client.get('/api/admin/content/records/'+r['id']).json();assert kept['title']==r['title'] and kept['tags']==[]
    assert kept['revision']>r['revision']
    assert client.post('/api/admin/tags',headers=csrf(client),json={'name':name}).status_code==409
    assert write(client,'/records/'+r['id'],update_payload(r,tag_ids=[tag['id']]),'put').status_code==409

def test_deleted_place_identity_cannot_be_recreated_by_old_raw_marker(client):
    name='合成删除地点-'+uuid.uuid4().hex[:12]
    place=client.post('/api/admin/archive/places',headers=csrf(client),json={'name':name,'category':'餐厅'}).json()
    response=client.request('DELETE','/api/admin/archive/places/'+place['id'],headers=csrf(client),json={'expected_revision':place['revision']})
    assert response.status_code==200,response.text
    t=make_type(client)
    response=write(client,'/records',payload(t,body='- @f '+name))
    assert response.status_code==422,response.text
    assert '删除' in response.text

def test_new_routes_keep_auth_admin_csrf_and_draft_isolation(client):
    from fastapi.testclient import TestClient
    from dataclasses import replace
    from app.main import create_app
    from app.models import User
    from app.security import ph
    from test_api import app,login
    username='v5-reader-'+uuid.uuid4().hex;password='SyntheticReaderV5'
    with SessionLocal() as db:db.add(User(username=username,password_hash=ph.hash(password)));db.commit()
    t=make_type(client);r=write(client,'/records',payload(t,title='隐藏草稿-'+uuid.uuid4().hex,status='draft',body='- @f 私人餐厅')).json()
    with TestClient(client.app,base_url='https://testserver') as anon:
        assert anon.get('/api/food').status_code==401
        assert anon.get(A+'/rules').status_code==401
        assert anon.post('/api/auth/login',headers=csrf(anon),json={'username':username,'password':password}).status_code==200
        assert anon.get(A+'/rules').status_code==403
        assert anon.post('/api/admin/food/install-template',headers=csrf(anon)).status_code==403
        assert anon.get('/api/food?q='+r['title']).json()['total']==0
        assert anon.get('/api/food/'+str(uuid.uuid4())).status_code==404
        assert anon.get('/api/admin/content/records?status=draft').status_code==403
    assert client.post(A+'/rules',json={'name':'缺少CSRF'}).status_code==403
    with TestClient(create_app(replace(app.state.settings,dynamic_blog_enabled=False)),base_url='https://testserver') as disabled:
        login(disabled)
        # Phase 4A retired the dynamic-feature flag; unified content stays usable.
        assert disabled.get(A+'/rules').status_code==200
        assert disabled.get('/api/food').status_code==200

@pytest.mark.skipif(__import__('test_api').engine.dialect.name!='postgresql',reason='real PostgreSQL advisory-lock concurrency')
def test_concurrent_archive_replay_moves_each_media_only_once(client):
    from concurrent.futures import ThreadPoolExecutor
    media=upload(client).json()
    rule=client.post(A+'/rules',headers=csrf(client),json={'name':'PG并发确认','enabled':True}).json()
    plan=client.post(A+'/rules/'+rule['id']+'/preview',headers=csrf(client),json={'items':[{'id':media['id'],'expected_revision':media['revision']}]}).json()
    headers=csrf(client)
    def run():return client.post(A+'/plans/'+plan['id']+'/execute',headers=headers,json={'confirmation':'确认逻辑归档'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(run) for _ in range(2)];results=[f.result(timeout=20) for f in futures]
    assert [r.status_code for r in results]==[200,200]
    assert sorted(r.json()['replayed'] for r in results)==[False,True]
    saved=client.get('/api/admin/archive/media/'+media['id']).json()
    assert saved['revision']==media['revision']+1 and saved['sha256']==media['sha256']

def test_trash_restore_and_permanent_article_purge_keep_folder_media_and_food_identity(client):
    from test_recovery import deleted,action
    from app.archive_models import MediaFolder
    t=make_type(client);m=upload(client).json()
    r=write(client,'/records',payload(t,title='v5恢复-'+uuid.uuid4().hex,body='- @f 合成恢复餐厅-'+uuid.uuid4().hex[:8],connections={'media':[{'id':m['id'],'cover':True}]})).json()
    folder=r['media_folder_id'];food=client.get('/api/food?q='+r['title']).json()['items'][0]
    changed=client.put('/api/admin/food/occurrences/'+food['id'],headers=csrf(client),json={'expected_revision':food['revision'],'city_override':'人工恢复城市','category':'保留分类'});assert changed.status_code==200
    d=deleted(client,r);assert client.get('/api/food?q='+r['title']).json()['total']==0
    assert action(client,[d],'restore').json()['items'][0]['state']=='restored'
    restored=client.get('/api/admin/content/records/'+r['id']).json();assert restored['media_folder_id']==folder
    food2=client.get('/api/food?q='+r['title']).json()['items'][0];assert food2['id']==food['id'] and food2['city']=='人工恢复城市'
    d=deleted(client,restored);assert action(client,[d],'purge').json()['items'][0]['state']=='purged'
    with SessionLocal() as db:
        assert db.get(RecordMediaFolder,r['id']) is None
        assert db.get(MediaFolder,folder) is not None and db.get(MediaAsset,m['id']) is not None
    assert client.get('/api/library-media/'+m['id']+'/original').status_code==200

def test_first_edit_of_legacy_article_adopts_only_requested_new_uploads(client):
    from sqlalchemy import delete
    t=make_type(client);r=write(client,'/records',payload(t,status='draft')).json()
    # An upgraded v4.2 row has no article-folder binding until its first save.
    old_folder=r['media_folder_id']
    with SessionLocal() as db:db.execute(delete(RecordMediaFolder).where(RecordMediaFolder.record_id==r['id']));db.commit()
    selected=upload(client).json();unselected=upload(client).json()
    edited=write(client,'/records/'+r['id'],update_payload(r,new_media_ids=[selected['id']]),'put');assert edited.status_code==200,edited.text
    new_folder=edited.json()['media_folder_id'];assert new_folder and new_folder!=old_folder
    assert client.get('/api/admin/archive/media/'+selected['id']).json()['folder_id']==new_folder
    assert client.get('/api/admin/archive/media/'+unselected['id']).json()['folder_id'] is None


def test_archive_uploaded_date_uses_utc_and_exif_date_remains_calendar_date():
    from types import SimpleNamespace
    from datetime import datetime,date
    from app.services.organization import path_for
    rule=SimpleNamespace(date_source='uploaded',fallback='unknown',granularity='day',by_type=False)
    media=SimpleNamespace(created_at=datetime.fromisoformat('2026-10-03T00:30:00+08:00'),captured_on=None)
    assert path_for(rule,media)==['2026','10','02']
    rule.date_source='captured';assert path_for(rule,media)==['拍摄日期未知']
    rule.fallback='uploaded';assert path_for(rule,media)==['2026','10','02']
    media.captured_on=date(2026,10,3);assert path_for(rule,media)==['2026','10','03']


def test_explicit_unfiled_upload_wins_over_enabled_auto_rule(client):
    from test_archive import image_bytes
    rule=client.post(A+'/rules',headers=csrf(client),json={'name':'自动规则不得覆盖明确选择','enabled':True});assert rule.status_code==200
    default=upload(client).json();assert default['folder_id']
    manual=client.post('/api/admin/archive/media',headers=csrf(client),files={'file':('synthetic-unfiled.jpg',image_bytes(),'image/jpeg')},data={'auto_archive':'false'})
    assert manual.status_code==200,manual.text
    assert manual.json()['folder_id'] is None
