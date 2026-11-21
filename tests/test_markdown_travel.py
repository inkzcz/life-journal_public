"""v4.2.0 synthetic full-save workflow, with no NAS/private material."""
import io,uuid
from PIL import Image
from sqlalchemy import select,func
from test_content import client,make_type,record_payload as base_payload,write,update_payload,field as base_field
from test_api import csrf,reset_limiter,SessionLocal
from app.archive_models import Place,MediaAsset,RecordMarkedPlace
from app.life_models import TripActivity
from app.services.itinerary import extract
from datetime import date

def record_payload(t,values=None,**changes):return {**base_payload(t,values),**changes}
def field(kind,**changes):return {**base_field(kind),**changes}

def reconcile(client,record):
    preview=client.post('/api/admin/content/records/'+record['id']+'/itinerary-sync-preview',headers=csrf(client),json={'expected_revision':record['revision'],'body':record['body']})
    assert preview.status_code==200,preview.text
    confirmed=client.post('/api/admin/content/records/'+record['id']+'/itinerary-sync-confirm',headers=csrf(client),json={'expected_revision':record['revision'],'body_hash':preview.json()['body_hash']})
    assert confirmed.status_code==200,confirmed.text
    return confirmed.json()

BODY='## 10月3日\n\n- @l 汉源 @f 游记黄牛肉\n  - 中午途经汉源。\n  - 味道不错。\n\n- @h 合成酒店\n  - 停车方便。\n\n## 第2天\n\n- @l 康定 @s 木格措\n  - 上午游玩。'

def test_nested_description_and_optional_time():
    result=extract(BODY,date(2026,10,3))
    assert len(result['items'])==3
    assert result['items'][0]['description']=='中午途经汉源。\n味道不错。'
    assert result['items'][0]['time'] is None
    assert result['items'][-1]['day']=='2026-10-04'

def test_marked_places_save_idempotency_and_managed_activity_sync(client):
    t=make_type(client)
    response=write(client,'/records',record_payload(t,body=BODY,life={'start_date':'2026-10-03'}))
    assert response.status_code==200,response.text
    r=response.json();assert len(r['connections']['places'])==5
    assert len(r['life']['activities'])==3 and r['life']['end_date'] is None
    assert r['life']['activities'][0]['place_id']
    with SessionLocal() as db:count=db.scalar(select(func.count()).select_from(Place))
    response=write(client,'/records/'+r['id'],update_payload(r,body=BODY,life=r['life'],connections={'places':[p['id'] for p in r['connections']['places']]}),'put')
    assert response.status_code==200,response.text
    r=response.json();assert len(r['life']['activities'])==3
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Place))==count
    response=write(client,'/records/'+r['id'],update_payload(r,body=BODY.replace('游记黄牛肉','合成新餐馆'),life=r['life']),'put')
    assert response.status_code==200,response.text
    # Editing the source alone preserves the old itinerary until diff confirmation.
    updated=reconcile(client,response.json())
    assert len(updated['life']['activities'])==3
    assert any('合成新餐馆' in a['title'] for a in updated['life']['activities'])
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(TripActivity).where(TripActivity.record_id==r['id']))==4
        assert db.scalar(select(func.count()).select_from(TripActivity).where(TripActivity.record_id==r['id'],TripActivity.active.is_(False)))==1


def test_marker_explicit_identity_and_code_is_inert(client):
    t=make_type(client)
    first=write(client,'/records',record_payload(t,body='@l 合成地区')).json();p=first['connections']['places'][0]
    body=f'@l 合成地区 {{#place:{p["id"]}}}\n\n```\n@f 不应创建\n```\n\n`@h 也不创建`'
    second=write(client,'/records',record_payload(t,body=body))
    assert second.status_code==200,second.text
    assert [x['id'] for x in second.json()['connections']['places']]==[p['id']]
    unknown=write(client,'/records',record_payload(t,body=f'@l 未知 {{#place:{uuid.uuid4()}}}'))
    assert unknown.status_code==422


def test_date_conflict_rejected_atomically_and_summary_optional(client):
    t=make_type(client,[field('date',name='出发日期')]);fid=t['fields'][0]['id']
    bad=write(client,'/records',record_payload(t,{fid:'2026-10-03'},body='@l 不可提交地点',life={'start_date':'2026-10-04'}))
    assert bad.status_code==422
    good=write(client,'/records',record_payload(t,{fid:'2026-10-03'},summary='只供列表使用的摘要',body='正文独立'))
    assert good.status_code==200,good.text
    assert good.json()['life']['start_date']=='2026-10-03' and good.json()['summary']=='只供列表使用的摘要'
    with SessionLocal() as db:assert db.scalar(select(Place).where(Place.name=='不可提交地点')) is None


def test_exif_date_and_preview_privacy(client):
    image=Image.new('RGB',(40,30),'blue');exif=Image.Exif();exif[36867]='2026:10:03 12:34:56';out=io.BytesIO();image.save(out,'JPEG',exif=exif)
    r=client.post('/api/admin/archive/media',headers=csrf(client),files={'file':('synthetic.jpg',out.getvalue(),'image/jpeg')})
    assert r.status_code==200,r.text
    asset=r.json();assert asset['captured_on']=='2026-10-03'
    preview=client.get('/api/library-media/'+asset['id']+'/preview');assert preview.status_code==200
    with Image.open(io.BytesIO(preview.content)) as clean:assert not clean.getexif()
    t=make_type(client);block=':::lj-media-v1\n'+__import__('json').dumps({'id':asset['id'],'widthPercent':60,'align':'right'})+'\n:::'
    r=write(client,'/records',record_payload(t,body=block,body_format=2))
    assert r.status_code==200,r.text
    assert r.json()['life']['photos'][0]['taken_on']=='2026-10-03'


def test_duplicate_places_require_explicit_identity_and_readonly_names_survive(client):
    name='同名餐厅-'+uuid.uuid4().hex[:8];region='合成地区-'+uuid.uuid4().hex[:8]
    def place():
        r=client.post('/api/admin/archive/places',headers=csrf(client),json={'name':name,'category':'餐厅','region':region});assert r.status_code==200;return r.json()
    a,b=place(),place();t=make_type(client)
    ambiguous=write(client,'/records',record_payload(t,body=f'@l {region} @f {name}'))
    assert ambiguous.status_code==422
    chosen=write(client,'/records',record_payload(t,body=f'@l {region} @f {name} {{#place:{b["id"]}}}'))
    assert chosen.status_code==200,chosen.text
    assert b['id'] in [p['id'] for p in chosen.json()['connections']['places']]
    assert a['id'] not in [p['id'] for p in chosen.json()['connections']['places']]


def test_two_concurrent_saves_create_one_place(client):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    t=make_type(client);name='并发地点-'+uuid.uuid4().hex
    cookies=dict(client.cookies)
    def save():
        with TestClient(client.app,base_url='https://testserver') as c:
            c.cookies.update(cookies)
            return write(c,'/records',record_payload(t,body='@l '+name))
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(save) for _ in range(2)]
        results=[f.result(timeout=20) for f in jobs]
    assert all(r.status_code==200 for r in results),[r.text for r in results]
    assert results[0].json()['connections']['places'][0]['id']==results[1].json()['connections']['places'][0]['id']
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Place).where(Place.name==name))==1


def test_product_versions_match():
    import json
    from pathlib import Path
    from app.version import __version__
    root=Path(__file__).parents[1]
    assert __version__==root.joinpath('VERSION').read_text().strip()
    assert json.loads(root.joinpath('frontend/package.json').read_text())['version']==__version__
    lock=json.loads(root.joinpath('frontend/package-lock.json').read_text())
    assert lock['version']==lock['packages']['']['version']==__version__
    assert f"VERSION='{__version__}'" in root.joinpath('frontend/src/version.ts').read_text()


def test_manual_activity_edits_are_not_overwritten_by_body_sync(client):
    t=make_type(client);r=write(client,'/records',record_payload(t,body=BODY,life={'start_date':'2026-10-03'})).json()
    life=r['life'];life['activities'][0]['description']='手动维护的重要补充'
    updated=write(client,'/records/'+r['id'],update_payload(r,body=BODY,life=life),'put')
    assert updated.status_code==200,updated.text
    assert updated.json()['life']['activities'][0]['description']=='手动维护的重要补充'


def test_conflicting_duplicate_date_fields_never_silently_choose_one(client):
    t=make_type(client,[field('date',name='出发日期',position=0),field('date',name='旅行开始日期',position=1)])
    values={t['fields'][0]['id']:'2026-10-03',t['fields'][1]['id']:'2026-10-04'}
    r=write(client,'/records',record_payload(t,values))
    assert r.status_code==422


def test_history_restore_keeps_exact_bindings_and_auto_activity_identity(client):
    t=make_type(client);r=write(client,'/records',record_payload(t,body=BODY,life={'start_date':'2026-10-03'})).json()
    old=r['life']['activities'];bindings=r['marked_places']
    changed=write(client,'/records/'+r['id'],update_payload(r,body=BODY.replace('合成酒店','另一家合成酒店'),life=r['life']),'put')
    assert changed.status_code==200,changed.text
    restored=client.post('/api/admin/recovery/history/'+r['id']+'/'+str(r['revision'])+'/restore',headers=csrf(client),json={'expected_revision':changed.json()['revision'],'scope':'full','confirmation':'恢复为新草稿'})
    assert restored.status_code==200,restored.text
    data=restored.json();assert data['body']==BODY and data['life']['activities']==old and data['marked_places']==bindings
    with SessionLocal() as db:
        assert all(db.get(TripActivity,a['id']).markdown_owned for a in old)


def test_two_explicit_same_name_places_never_share_activity_binding(client):
    name='同城不同店-'+uuid.uuid4().hex[:8]
    def create():
        r=client.post('/api/admin/archive/places',headers=csrf(client),json={'name':name,'category':'餐厅'});assert r.status_code==200;return r.json()['id']
    a,b=create(),create();t=make_type(client)
    body=f'## 2026-10-03\n\n- @f {name} {{#place:{a}}}\n\n- @f {name} {{#place:{b}}}'
    r=write(client,'/records',record_payload(t,body=body,life={'start_date':'2026-10-03'}))
    assert r.status_code==200,r.text
    assert {x['place_id'] for x in r.json()['marked_places']}=={a,b}
    assert [x['place_id'] for x in r.json()['life']['activities']]==[a,b]


def test_removing_marks_unlinks_only_derived_places_and_keeps_resources_history(client):
    manual=client.post('/api/admin/archive/places',headers=csrf(client),json={'name':'手工地点-'+uuid.uuid4().hex}).json()
    t=make_type(client);r=write(client,'/records',record_payload(t,body='## 2026-10-03\n\n- @f 自动餐厅-'+uuid.uuid4().hex,life={'start_date':'2026-10-03'},connections={'places':[manual['id']]})).json()
    automatic=next(p['id'] for p in r['connections']['places'] if p['id']!=manual['id'])
    changed=write(client,'/records/'+r['id'],update_payload(r,body='正文不再包含地点标记。',life=r['life']),'put')
    assert changed.status_code==200,changed.text
    assert changed.json()['life']['activities']  # No implicit deletion on save.
    reconciled=reconcile(client,changed.json())
    assert [p['id'] for p in reconciled['connections']['places']]==[manual['id']]
    assert not reconciled['life']['activities']
    with SessionLocal() as db:
        assert db.get(Place,automatic) is not None
        from app.content_models import RecordRevision
        old=db.get(RecordRevision,(r['id'],1)).snapshot
        assert automatic in [p['id'] for p in old['connections']['places']]


def test_private_image_blocks_never_become_itinerary_activities():
    body=BODY+'\n\n:::lj-media-v1\n{"id":"11111111-1111-4111-8111-111111111111"}\n:::\n'
    result=extract(body,date(2026,10,3))
    assert len(result['items'])==3
    assert all(x['title']!=':::' for x in result['items'])


def test_adopted_dates_still_validate_activity_range_as_422(client):
    t=make_type(client,[field('date',name='出发日期')]);fid=t['fields'][0]['id']
    r=write(client,'/records',record_payload(t,{fid:'2026-10-03'},life={'activities':[{'id':str(uuid.uuid4()),'day':'2026-10-02','title':'范围外活动'}]}))
    assert r.status_code==422


def test_compact_and_bracket_marks_reuse_places_and_leave_prose_intact(client):
    from app.services.markdown_marks import parse
    body="途经@l汉源县 @f[Joe's Pizza] 然后出发\n\n`@s不解析`\n\nhttps://example.com/@h酒店"
    assert [(m['kind'],m['name']) for m in parse(body).marks]==[('l','汉源县'),('f',"Joe's Pizza")]
    t=make_type(client)
    response=write(client,'/records',record_payload(t,body=body))
    assert response.status_code==200,response.text
    r=response.json();assert r['body']==body and len(r['connections']['places'])==2
    again=write(client,'/records/'+r['id'],update_payload(r,body=body),'put')
    assert again.status_code==200,again.text
    assert {p['id'] for p in again.json()['connections']['places']}=={p['id'] for p in r['connections']['places']}
    pid=r['connections']['places'][0]['id']
    explicit=write(client,'/records',record_payload(t,body=f'@l[汉源县] {{#place:{pid}}} 正文保留'))
    assert explicit.status_code==200,explicit.text
    assert explicit.json()['connections']['places'][0]['id']==pid
