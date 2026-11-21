"""Runs only against an isolated temporary SQLite database; optional PostgreSQL URL.
TEST_DATABASE_URL must point to a disposable, empty database (tables are created).
"""
import io
import os
import secrets
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sandbox = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = os.getenv('TEST_DATABASE_URL', 'sqlite:///' + sandbox.name + '/test.db')
os.environ['MEDIA_DIR'] = sandbox.name + '/media'
os.environ['COOKIE_SECURE'] = 'true'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.db import SessionLocal, engine
from app.migrations import upgrade
upgrade(engine)
from app.main import app
# Retained legacy fixture: exercise archival CRUD/security against an explicit
# test-only router registration. Production create_app no longer mounts these.
from legacy_backend import journals as legacy_journals, media as legacy_media
app.include_router(legacy_journals.router)
app.include_router(legacy_media.router)
from app.security import ph, digest
MEDIA_DIR = app.state.settings.media_dir
from app.models import User, Session, AdminUser

PASSWORD = secrets.token_urlsafe(24)
with SessionLocal() as db:
    user=User(username='test-admin', password_hash=ph.hash(PASSWORD))
    db.add(user);db.flush()
    db.add(AdminUser(user_id=user.id))
    db.commit()

@pytest.fixture(autouse=True)
def reset_limiter():
    from app.security import login_attempts
    login_attempts.clear()
    yield
    login_attempts.clear()

@pytest.fixture
def client():
    with TestClient(app, base_url='https://testserver') as c:
        yield c

def csrf(c):
    token = c.get('/api/auth/csrf').json()['csrf_token']
    return {'x-csrf-token': token}

def login(c):
    headers = csrf(c)
    r = c.post('/api/auth/login', json={'username': 'test-admin', 'password': PASSWORD}, headers=headers)
    assert r.status_code == 200
    return headers

@pytest.mark.parametrize('path', ['/api/auth/me', '/api/journals', '/api/journals/1', '/api/journals/1/media', '/api/media/any'])
def test_anonymous_read_denied(client, path):
    assert client.get(path).status_code == 401

@pytest.mark.parametrize('method,path', [('post','/api/journals'), ('put','/api/journals/1'), ('delete','/api/journals/1'), ('post','/api/journals/1/media')])
def test_anonymous_mutation_denied(client, method, path):
    assert getattr(client, method)(path, headers=csrf(client)).status_code == 401

def test_auth_and_csrf(client):
    assert client.post('/api/auth/login', json={}).status_code == 403
    h = csrf(client)
    assert client.post('/api/auth/login', headers=h, json={'username':'test-admin','password':'wrong'}).status_code == 401
    login(client)
    assert client.get('/api/auth/me').json() == {'username':'test-admin'}
    assert client.post('/api/journals', json={'title':'a'}).status_code == 403
    assert client.post('/api/journals', headers={**h, 'sec-fetch-site':'cross-site'}, json={'title':'a'}).status_code == 403
    cookie = client.cookies.get('life_session')
    assert client.post('/api/auth/logout', headers=h).status_code == 200
    client.cookies.set('life_session', cookie)
    assert client.get('/api/auth/me').status_code == 401

def test_crud_media_and_persistence(client):
    h = login(client)
    assert client.post('/api/journals', headers=h, json={'title':'   '}).status_code == 422
    r = client.post('/api/journals', headers=h, json={'title':' 测试 ', 'content':'# Markdown\n私人日记'})
    assert r.status_code == 200
    j = r.json(); jid = j['id']
    assert j['title'] == '测试'
    path = f'/api/journals/{jid}'
    assert client.put(path, headers=h, json={'title':'更新','content':'**粗体**'}).status_code == 200
    # A fresh authenticated HTTP client sees committed database state.
    with TestClient(app, base_url='https://testserver') as second:
        login(second)
        assert second.get(path).json()['content'] == '**粗体**'
        assert any(x['id'] == jid for x in second.get('/api/journals').json())
    data = io.BytesIO(); Image.new('RGB',(4,4)).save(data, format='PNG')
    r = client.post(path+'/media', headers=h, files={'file':('photo.png',data.getvalue(),'image/png')})
    assert r.status_code == 200
    mid = r.json()['id']
    assert client.get(path+'/media').json() == [{'id':mid,'filename':'photo.png'}]
    photo = client.get('/api/media/'+mid)
    assert photo.content == data.getvalue()
    assert photo.headers['cache-control'] == 'no-store'
    with TestClient(app, base_url='https://testserver') as anon:
        assert anon.get('/api/media/'+mid).status_code == 401
    assert client.post(path+'/media', headers=h, files={'file':('bad.png',b'not an image','image/png')}).status_code == 415
    assert client.post(path+'/media', headers=h, files={'file':('big.png',b'x'*(10*1024*1024+1),'image/png')}).status_code == 413
    assert client.delete(path, headers=h).status_code == 200
    assert client.get(path).status_code == 404
    assert client.get('/api/media/'+mid).status_code == 404
    assert not (MEDIA_DIR/mid).exists()

def test_expired_session(client):
    with SessionLocal() as db:
        user = db.query(User).filter_by(username='test-admin').one()
        token = secrets.token_urlsafe(32)
        db.add(Session(user_id=user.id, token_hash=digest(token), expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)))
        db.commit()
    client.cookies.set('life_session',token)
    assert client.get('/api/auth/me').status_code == 401

def test_secure_cookie_and_health(client):
    h = csrf(client)
    r = client.post('/api/auth/login', headers=h, json={'username':'test-admin','password':PASSWORD})
    cookie = r.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'secure' in cookie and 'samesite=strict' in cookie
    assert client.get('/api/health').json() == {'ok':True}

def test_decompression_bomb_rejected(client, monkeypatch):
    h = login(client)
    jid = client.post('/api/journals', headers=h, json={'title':'size validation'}).json()['id']
    data = io.BytesIO(); Image.new('RGB',(4,4)).save(data, format='PNG')
    monkeypatch.setattr(Image, 'MAX_IMAGE_PIXELS', 1)
    assert client.post(f'/api/journals/{jid}/media', headers=h, files={'file':('bomb.png', data.getvalue(),'image/png')}).status_code == 415
    assert client.delete(f'/api/journals/{jid}', headers=h).status_code == 200

def test_database_password_special_characters(monkeypatch):
    from app.db import database_url
    monkeypatch.delenv('DATABASE_URL')
    monkeypatch.setenv('POSTGRES_USER', 'test')
    monkeypatch.setenv('POSTGRES_DB', 'test')
    password = secrets.token_urlsafe(16) + '@:/?#%'
    monkeypatch.setenv('POSTGRES_PASSWORD', password)
    url = database_url()
    assert url.password == password
    assert url.host == 'db'
    from sqlalchemy.engine import make_url
    assert make_url(url.render_as_string(hide_password=False)).password == password


def test_login_throttling_and_recovery(client, monkeypatch):
    import app.security as main
    headers = csrf(client)
    for _ in range(10):
        assert client.post('/api/auth/login',headers=headers,json={'username':'missing','password':'wrong'}).status_code == 401
    r = client.post('/api/auth/login',headers=headers,json={'username':'test-admin','password':PASSWORD})
    assert r.status_code == 429
    assert r.headers['retry-after'] == '60'
    now = main.monotonic()
    monkeypatch.setattr(main, 'monotonic', lambda: now+61)
    assert client.post('/api/auth/login',headers=headers,json={'username':'test-admin','password':PASSWORD}).status_code == 200

def test_failed_delete_keeps_database_and_photo(client, monkeypatch):
    h = login(client)
    jid = client.post('/api/journals',headers=h,json={'title':'rollback safety'}).json()['id']
    path=f'/api/journals/{jid}'
    data=io.BytesIO(); Image.new('RGB',(4,4)).save(data,format='PNG')
    mid=client.post(path+'/media',headers=h,files={'file':('test.png',data.getvalue(),'image/png')}).json()['id']
    def fail_commit(self):
        raise RuntimeError('simulated database failure')
    with monkeypatch.context() as patch:
        patch.setattr(SessionLocal.class_, 'commit', fail_commit)
        with pytest.raises(RuntimeError, match='simulated database failure'):
            client.delete(path,headers=h)
    assert client.get(path).status_code==200
    assert client.get('/api/media/'+mid).content==data.getvalue()
    assert client.delete(path,headers=h).status_code==200

@pytest.mark.parametrize('path', ['/api/journals/page','/api/journals/filters'])
def test_browsing_requires_login(client,path):
    assert client.get(path).status_code==401


def test_paging_search_dates_and_metadata(client):
    h=login(client)
    marker='phase2-'+secrets.token_hex(6)
    ids=[]
    for day in ['2026-01-01','2026-01-03','2026-01-03']:
        r=client.post('/api/journals',headers=h,json={
            'title':marker+' '+day,'content':'正文 Life_100% 检索',
            'entry_date':day,'category':' 日常 ','tags':[' 心情 ','阅读','心情'],
        })
        assert r.status_code==200
        j=r.json();ids.append(j['id'])
        assert j['category']=='日常' and j['tags']==['心情','阅读']
    params={'q':marker,'page_size':2}
    first=client.get('/api/journals/page',params=params).json()
    second=client.get('/api/journals/page',params={**params,'page':2}).json()
    assert first['total']==3 and len(first['items'])==2 and len(second['items'])==1
    assert [j['id'] for j in first['items']+second['items']]==list(reversed(ids))
    assert all('content' not in j for j in first['items'])
    filtered=client.get('/api/journals/page',params={**params,'date_from':'2026-01-03','date_to':'2026-01-03','category':'日常','tag':'阅读'}).json()
    assert filtered['total']==2
    assert client.get('/api/journals/page',params={**params,'tag':'不存在'}).json()['total']==0
    assert client.get('/api/journals/page',params={**params,'category':'不存在'}).json()['total']==0
    facets=client.get('/api/journals/filters').json()
    assert '日常' in facets['categories'] and '阅读' in facets['tags']
    # Search punctuation is literal, never SQL wildcard expansion.
    assert client.get('/api/journals/page',params={'q':'Life_100%'}).json()['total']==3
    assert client.get('/api/journals/page',params={'q':'Life_100X'}).json()['total']==0
    assert client.get('/api/journals/page',params={**params,'page':999}).json()['items']==[]
    for jid in ids:
        assert client.delete(f'/api/journals/{jid}',headers=h).status_code==200


@pytest.mark.parametrize('params', [
    {'page':0},{'page_size':0},{'page_size':101},{'date_from':'bad'},
    {'date_from':'2026-02-01','date_to':'2026-01-01'},{'q':'x'*201},
])
def test_browsing_validation(client,params):
    login(client)
    assert client.get('/api/journals/page',params=params).status_code==422


@pytest.mark.parametrize('extra', [
    {'tags':['']},{'tags':['x'*41]},{'tags':[str(i) for i in range(11)]},
    {'category':'x'*81},{'entry_date':'not-a-date'},
])
def test_metadata_validation(client,extra):
    h=login(client)
    assert client.post('/api/journals',headers=h,json={'title':'validation',**extra}).status_code==422


def test_legacy_data_compatible_and_metadata_update(client):
    from app.models import Journal,JournalMetadata,JournalTag
    from sqlalchemy import select
    marker='legacy-'+secrets.token_hex(6)
    original=datetime(2025,12,31,20,0,tzinfo=timezone.utc)
    with SessionLocal() as db:
        j=Journal(title=marker,content='旧正文',created_at=original,updated_at=original)
        db.add(j);db.commit();jid=j.id
    h=login(client);path=f'/api/journals/{jid}'
    detail=client.get(path).json()
    assert detail['entry_date']=='2026-01-01' and detail['category']=='' and detail['tags']==[]
    result=client.get('/api/journals/page',params={'q':marker,'date_from':'2026-01-01','date_to':'2026-01-01'}).json()
    assert result['total']==1
    with SessionLocal() as db:
        assert db.get(JournalMetadata,jid) is None  # No read-time backfill.
        assert db.get(Journal,jid).content=='旧正文'
    updated=client.put(path,headers=h,json={'title':marker,'content':'新正文','entry_date':'2024-05-01','category':'阅读','tags':['书']}).json()
    assert updated['entry_date']=='2024-05-01'
    # Older clients can still update content without erasing new metadata.
    updated=client.put(path,headers=h,json={'title':marker,'content':'旧客户端更新'}).json()
    assert updated['category']=='阅读' and updated['tags']==['书'] and updated['entry_date']=='2024-05-01'
    updated=client.put(path,headers=h,json={'title':marker,'category':'','tags':[]}).json()
    assert updated['category']=='' and updated['tags']==[]
    assert client.delete(path,headers=h).status_code==200
    with SessionLocal() as db:
        assert db.get(JournalMetadata,jid) is None
        assert db.scalar(select(JournalTag).where(JournalTag.journal_id==jid)) is None


def test_page_batches_metadata_without_loading_bodies(client):
    from sqlalchemy import event
    h=login(client)
    marker='batch-'+secrets.token_hex(6)
    for _ in range(5):
        assert client.post('/api/journals',headers=h,json={'title':marker,'content':'large private body','tags':['批量']}).status_code==200
    statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        statements.append(statement)
    event.listen(engine,'before_cursor_execute',capture)
    try:
        result=client.get('/api/journals/page',params={'category':'','date_from':'2000-01-01'})
        assert result.status_code==200
    finally:
        event.remove(engine,'before_cursor_execute',capture)
    assert len(statements)<=6  # Auth/session, count, page, metadata and tags.
    assert all('journals.content' not in statement for statement in statements)


def test_admin_status_and_legacy_auth_shape(client):
    assert client.get('/api/admin/status').status_code==401
    login(client)
    assert client.get('/api/auth/me').json()=={'username':'test-admin'}
    assert client.get('/api/admin/status').json()=={
        'username':'test-admin','is_admin':True,'features':{'dynamic_blog':True}}


@pytest.fixture
def reader_credentials():
    username='reader-'+secrets.token_hex(8)
    password=secrets.token_urlsafe(24)
    with SessionLocal.begin() as db:
        user=User(username=username,password_hash=ph.hash(password))
        db.add(user);db.flush();uid=user.id
    return username,password,uid


def reader_login(client,credentials):
    username,password,_=credentials
    h=csrf(client)
    assert client.post('/api/auth/login',headers=h,json={'username':username,'password':password}).status_code==200
    return h


def test_readers_cannot_manage_or_mutate(client,reader_credentials):
    h=login(client)
    j=client.post('/api/journals',headers=h,json={'title':'permission protection','content':'preserved'}).json()
    jid=j['id']
    data=io.BytesIO();Image.new('RGB',(4,4)).save(data,format='PNG')
    mid=client.post(f'/api/journals/{jid}/media',headers=h,files={'file':('test.png',data.getvalue(),'image/png')}).json()['id']
    with TestClient(app,base_url='https://testserver') as reader:
        headers=reader_login(reader,reader_credentials)
        for path in ['/api/journals','/api/journals/page','/api/journals/filters',f'/api/journals/{jid}',f'/api/journals/{jid}/media',f'/api/media/{mid}']:
            assert reader.get(path).status_code==200
        assert reader.get('/api/admin/status',headers={'x-is-admin':'true'}).status_code==403
        assert reader.post('/api/journals',headers=headers,json={'title':'blocked','is_admin':True}).status_code==403
        assert reader.put(f'/api/journals/{jid}',headers=headers,json={'title':'blocked'}).status_code==403
        assert reader.delete(f'/api/journals/{jid}',headers=headers).status_code==403
        assert reader.post(f'/api/journals/{jid}/media',headers=headers,files={'file':('x.png',data.getvalue(),'image/png')}).status_code==403
        assert reader.post('/api/admin/grant',headers=headers,json={'username':reader_credentials[0]}).status_code==404
        assert reader.post('/api/auth/logout',headers=headers).status_code==200
    assert client.get(f'/api/journals/{jid}').json()['content']=='preserved'
    assert client.get(f'/api/media/{mid}').content==data.getvalue()
    assert client.delete(f'/api/journals/{jid}',headers=h).status_code==200


def test_explicit_admin_grant_is_idempotent_and_session_permissions_refresh(client,reader_credentials):
    from app.manage_admin import grant_admin
    username,password,uid=reader_credentials
    reader_login(client,reader_credentials)
    token=client.cookies.get('life_session')
    assert client.get('/api/admin/status').status_code==403
    with SessionLocal() as db:
        original_hash=db.get(User,uid).password_hash
    grant_admin(username)
    with SessionLocal() as db:
        granted_at=db.get(AdminUser,uid).granted_at
    grant_admin(username)
    with SessionLocal() as db:
        assert db.get(User,uid).password_hash==original_hash
        assert db.get(AdminUser,uid).granted_at==granted_at
    assert client.cookies.get('life_session')==token
    assert client.get('/api/admin/status').status_code==200
    with SessionLocal.begin() as db:
        db.delete(db.get(AdminUser,uid))
    assert client.get('/api/admin/status').status_code==403
    assert client.get('/api/auth/me').status_code==200
    with pytest.raises(ValueError,match='用户不存在'):
        grant_admin('nonexistent-'+secrets.token_hex(8))


@pytest.mark.parametrize('enabled',[False,True])
def test_dynamic_blog_switch_never_bypasses_admin(enabled,reader_credentials):
    from dataclasses import replace
    from fastapi import Depends
    from app.main import create_app
    from app.dependencies import require_dynamic_blog
    application=create_app(replace(app.state.settings,dynamic_blog_enabled=enabled))
    @application.get('/test-only-future-capability',dependencies=[Depends(require_dynamic_blog)])
    def future():
        return {'ok':True}
    with TestClient(application,base_url='https://testserver') as c:
        assert c.get('/test-only-future-capability').status_code==401
        reader_login(c,reader_credentials)
        assert c.get('/test-only-future-capability').status_code==403
        c.cookies.clear();login(c)
        assert c.get('/test-only-future-capability').status_code==200
        assert c.get('/api/admin/status').json()['features']['dynamic_blog'] is True
        assert c.get('/api/journals/page').status_code==404
        assert c.get('/api/content-types').status_code==404


def test_invalid_feature_flag_fails_closed(monkeypatch):
    from app.settings import Settings
    monkeypatch.setenv('DYNAMIC_BLOG_ENABLED','unexpected')
    assert Settings.from_env().dynamic_blog_enabled is True
    monkeypatch.setenv('COOKIE_SECURE','unexpected')
    with pytest.raises(ValueError,match='COOKIE_SECURE'):
        Settings.from_env()
