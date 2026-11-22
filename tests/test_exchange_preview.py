"""Real endpoints, CSRF, dynamic schemas, no permanent preview writes."""
import io,json,zipfile
from sqlalchemy import select,func
from test_content import client,make_type,field
from test_api import reset_limiter,csrf,SessionLocal
from app.content_models import ContentRecord
from app.archive_models import MediaAsset
from app.exchange.schemas import Exchange
from app.exchange.preview import preview

def payload(t):return {'format':'life-journal.exchange','version':1,'records':[{'key':'one','type_slug':t['slug'],'title':'合成预览','display_date':'2026-11-05','body':'普通正文','tags':['真实标签']} ]}
def test_export_inspect_and_confirmed_no_permanent_preview_rows(client):
    t=make_type(client)
    with SessionLocal() as db:counts=[db.scalar(select(func.count()).select_from(x)) for x in (ContentRecord,MediaAsset)]
    r=client.post('/api/admin/exchange/specification',json={'type_slug':t['slug']},headers=csrf(client))
    assert r.status_code==200 and r.headers['content-type']=='application/zip'
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:assert json.loads(z.read('context.json'))['type']['id']==t['id']
    r=client.post('/api/admin/exchange/inspect',files={'file':('x.json',json.dumps(payload(t)).encode(),'application/json')},headers=csrf(client))
    assert r.status_code==200 and r.json()['valid'] and r.json()['records'][0]['status']=='draft'
    with SessionLocal() as db:assert counts==[db.scalar(select(func.count()).select_from(x)) for x in (ContentRecord,MediaAsset)]

def test_preview_errors_and_required_preferences_never_invent_dates(client):
    t=make_type(client,fields=[field('short_text',required=True)])
    raw=payload(t);raw['records'][0]['display_date']=None
    with SessionLocal() as db:r=preview(db,Exchange.model_validate(raw),rule_layers=({'require_end':True},))
    assert not r['valid'] and r['records'][0]['display_date'] is None
    assert any(x['scope'].endswith('end_date') and x['level']=='warning' for x in r['issues'])
    raw['records'][0]['values']={'invented':'value'}
    with SessionLocal() as db:r=preview(db,Exchange.model_validate(raw))
    assert not r['valid'] and '未匹配' in str(r['issues'])

def test_raw_guessed_media_and_escaped_marks_are_not_silently_accepted(client):
    t=make_type(client);raw=payload(t);raw['records'][0]['body']='\\@f 字面示例'
    with SessionLocal() as db:r=preview(db,Exchange.model_validate(raw))
    assert not r['valid'] and '转义' in str(r['issues'])
    raw['records'][0]['body']='`@f 字面示例`'
    with SessionLocal() as db:assert preview(db,Exchange.model_validate(raw))['valid']

def test_inspection_requires_csrf(client):
    t=make_type(client)
    assert client.post('/api/admin/exchange/inspect',files={'file':('x.json',json.dumps(payload(t)).encode())}).status_code==403


def test_placeholder_code_and_escape_are_not_business_references():
    from app.exchange.preview import placeholders
    assert placeholders('```md\n{{media:fake}}\n```\n\n`{{media:fake}}`\n\n\\{{media:fake}}')==[]
    assert placeholders('{{media:real}}\n\n{{place:city}}')==[{'kind':'media','key':'real','line':0},{'kind':'place','key':'city','line':2}]


def test_reader_and_anonymous_cannot_export_or_inspect(client):
    import uuid
    from fastapi.testclient import TestClient
    from test_api import User,ph
    with TestClient(client.app,base_url='https://testserver') as anon:
        assert anon.post('/api/admin/exchange/specification',json={'type_slug':'x'},headers=csrf(anon)).status_code==401
    username='exchange-reader-'+uuid.uuid4().hex;password=uuid.uuid4().hex
    with SessionLocal() as db:db.add(User(username=username,password_hash=ph.hash(password)));db.commit()
    with TestClient(client.app,base_url='https://testserver') as reader:
        assert reader.post('/api/auth/login',headers=csrf(reader),json={'username':username,'password':password}).status_code==200
        assert reader.post('/api/admin/exchange/specification',json={'type_slug':'x'},headers=csrf(reader)).status_code==403
        assert reader.post('/api/admin/exchange/inspect',files={'file':('x.json',b'{}')},headers=csrf(reader)).status_code==403


def test_real_photo_package_preview_uses_existing_image_rules_without_assets(client):
    from pathlib import Path
    t=make_type(client)
    from scripts.demo_fixtures import example_bytes
    data=example_bytes(Path(__file__).resolve().parents[1])
    with zipfile.ZipFile(io.BytesIO(data)) as z:files={name:z.read(name) for name in z.namelist()}
    document=json.loads(files['travel.json']);document['records'][0]['type_slug']=t['slug'];files['travel.json']=json.dumps(document).encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    with SessionLocal() as db:before=db.scalar(select(func.count()).select_from(MediaAsset))
    r=client.post('/api/admin/exchange/inspect',files={'file':('travel.zip',out.getvalue(),'application/zip')},headers=csrf(client))
    assert r.status_code==200 and r.json()['valid'] and len(r.json()['images'])==2
    assert all(x['original_preserved'] and x['preview_strips_exif'] and x['mime_type']=='image/webp' for x in r.json()['images'])
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(MediaAsset))==before
    files['photos/plate-a.jpg']=b'<svg onload="evil()"></svg>';out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for name,data in files.items():z.writestr(name,data)
    assert client.post('/api/admin/exchange/inspect',files={'file':('bad.zip',out.getvalue())},headers=csrf(client)).status_code==415


def test_import_proxy_cap_is_narrow_and_csp_unchanged():
    from pathlib import Path
    text=(Path(__file__).resolve().parents[1]/'frontend/Caddyfile').read_text()
    assert 'handle /api/admin/exchange/inspect {' in text and 'max_size 51MB' in text
    assert 'handle /api/* {' in text and 'max_size 11MB' in text
    assert "style-src 'self'" in text and 'unsafe-inline' not in text


def test_unknown_format_errors_do_not_echo_rejected_private_values(client):
    t=make_type(client);raw=payload(t);raw['version']=999;raw['private_extra']='PRIVATE_NEVER_ECHO'
    r=client.post('/api/admin/exchange/inspect',files={'file':('x.json',json.dumps(raw).encode())},headers=csrf(client))
    assert r.status_code==422 and '版本' in r.text and 'PRIVATE_NEVER_ECHO' not in r.text
    assert all('input' not in e and 'ctx' not in e for e in r.json()['detail']['errors'])


def test_ordinary_markdown_image_uuid_requires_explicit_media_manifest(client):
    import uuid
    t=make_type(client);raw=payload(t);id=str(uuid.uuid4())
    raw['records'][0]['body']='![猜测图片](/api/library-media/'+id+'/preview)'
    with SessionLocal() as db:
        result=preview(db,Exchange.model_validate(raw))
        assert not result['valid'] and any('UUID' in i['message'] for i in result['issues'])
    raw['records'][0]['body']='```markdown\n![字面示例](/api/library-media/'+id+'/preview)\n```'
    with SessionLocal() as db:assert preview(db,Exchange.model_validate(raw))['valid']


def test_plain_markdown_preview_detects_deleted_place_without_recreating_it(client):
    import uuid
    name='已删除的合成地点-'+uuid.uuid4().hex[:8]
    place=client.post('/api/admin/archive/places',headers=csrf(client),json={'name':name}).json()
    assert client.request('DELETE','/api/admin/archive/places/'+place['id'],headers=csrf(client),json={'expected_revision':place['revision']}).status_code==200
    t=make_type(client);raw=payload(t);raw['records'][0]['body']='@l '+name
    with SessionLocal() as db:
        result=preview(db,Exchange.model_validate(raw))
        assert not result['valid'] and any('已从库中删除' in i['message'] for i in result['issues'])
