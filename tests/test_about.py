import json
from test_content import client
from test_api import csrf,reset_limiter
from app import build_info

def test_about_defaults_admin_save_roundtrip_csrf_and_conflict(client):
    current=client.get('/api/blog/about');assert current.status_code==200
    data={k:v for k,v in current.json().items() if k!='revision'}|{'body':'## 合成介绍\n\n原文保留','expected_revision':current.json()['revision']}
    assert client.put('/api/admin/blog/about',json=data).status_code==403
    response=client.put('/api/admin/blog/about',headers=csrf(client),json=data);assert response.status_code==200,response.text
    assert client.get('/api/blog/about').json()['body']==data['body']
    assert client.put('/api/admin/blog/about',headers=csrf(client),json=data).status_code==409
    assert client.put('/api/admin/blog/about',headers=csrf(client),json={**data,'css':'bad'}).status_code==422

def test_baked_metadata_whitelist_zip_identity_and_no_environment_spoof(tmp_path,monkeypatch):
    path=tmp_path/'metadata.json';monkeypatch.setattr(build_info,'METADATA',path)
    monkeypatch.setenv('LIFE_JOURNAL_VERSION','secret-runtime-not-a-version')
    assert build_info.build_info()['fingerprint'] is None
    data={'version':build_info.__version__,'revision':'a'*40,'revision_verified':False,'revision_source':'user-provided-zip','build_identity':'b'*40,'built_at':'2026-10-29T00:00:00Z','database_url':'must-not-leak'}
    path.write_text(json.dumps(data));public=build_info.build_info();private=build_info.build_info(True)
    assert public['short_revision']=='a'*7 and not public['revision_verified']
    assert 'revision' not in public and 'build_identity' not in public and 'database_url' not in public
    assert private['revision']=='a'*40 and public['fingerprint']==private['fingerprint']
    data.update(revision_source='git-head',revision_verified=True)
    path.write_text(json.dumps(data));assert build_info.build_info()['fingerprint'] is None
    data['build_identity']=data['revision'];path.write_text(json.dumps(data));assert build_info.build_info()['revision_verified']
    assert 'must-not-leak' not in json.dumps(build_info.build_info(True))

def test_release_notes_match_controlled_changelog():
    from pathlib import Path
    from scripts.sync_release_notes import generate,ROOT
    assert json.loads(build_info.NOTES.read_text())==generate((ROOT/'CHANGELOG.md').read_text())

def test_local_image_metadata_preserves_provenance():
    from scripts.local_images import build_metadata
    source={'revision':'a'*40,'build_identity':'b'*40,'revision_verified':False,'revision_source':'user-provided-zip'}
    data=build_metadata(source['revision'],source)
    assert not data['revision_verified'] and data['revision']==source['revision']
    assert data['built_at'].endswith('Z') and data['version']==build_info.__version__

def test_about_and_build_info_are_private_and_full_sha_is_admin_only(client,tmp_path,monkeypatch):
    import secrets,uuid
    from datetime import datetime,timedelta,timezone
    from fastapi.testclient import TestClient
    from test_api import app,SessionLocal
    from app.models import User,Session
    from app.security import digest
    metadata=tmp_path/'build.json';metadata.write_text(json.dumps({'version':build_info.__version__,'revision':'c'*40,'build_identity':'c'*40,'revision_verified':True,'revision_source':'git-head','built_at':'2026-10-29T00:00:00Z'}));monkeypatch.setattr(build_info,'METADATA',metadata)
    assert client.get('/api/blog/build-info').json()['revision']=='c'*40
    token=secrets.token_urlsafe(32)
    with SessionLocal() as db:
        user=User(username='reader-'+uuid.uuid4().hex,password_hash='synthetic');db.add(user);db.flush();db.add(Session(user_id=user.id,token_hash=digest(token),expires_at=datetime.now(timezone.utc)+timedelta(hours=1)));db.commit()
    with TestClient(app,base_url='https://testserver') as reader:
        assert reader.get('/api/blog/about').status_code==401
        assert reader.get('/api/blog/build-info').status_code==401
        reader.cookies.set('life_session',token)
        public=reader.get('/api/blog/build-info');assert public.status_code==200 and 'revision' not in public.json()
        assert public.json()['short_revision']=='c'*7
        assert reader.put('/api/admin/blog/about',headers=csrf(reader),json={'expected_revision':0}).status_code==403

def test_api_dockerfile_keeps_baked_metadata_root_owned_after_application_chown():
    from pathlib import Path
    text=(Path(__file__).resolve().parents[1]/'backend/Dockerfile').read_text()
    assert text.index('chown -R appuser:appuser /data /app') < text.index('chown root:root /app/BUILD_INFO.json')
    assert 'chmod 0444 /app/BUILD_INFO.json' in text
