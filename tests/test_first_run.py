"""Phase4A bootstrap tests. Only unique synthetic test DBs/schemas are used."""
import os,secrets,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine,text,select,inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).parents[1]/'backend'))
os.environ.setdefault('DATABASE_URL','sqlite://')
from app.passwords import validate_password
from app.migrations import initialize_empty_database,HEAD

@pytest.mark.parametrize('password',['1234567','password','12345678','aaaaaaaa','ｐａｓｓｗｏｒｄ','qwertyuiop',' password '])
def test_weak_passwords_rejected(password):
    with pytest.raises(ValueError):validate_password(password)

@pytest.mark.parametrize('password',['QuietFox','QuietFoxWithLongWords','生活里值得收藏的片刻','café旅途散步'])
def test_passwords_unicode_no_composition_requirement(password):
    assert validate_password(password)==password

@pytest.fixture
def fresh_pg():
    url=os.getenv('TEST_DATABASE_URL')
    if not url or make_url(url).get_backend_name()!='postgresql':pytest.skip('requires disposable PostgreSQL')
    admin=create_engine(url,isolation_level='AUTOCOMMIT')
    name='phase4a_test_'+secrets.token_hex(6)
    with admin.connect() as con:con.execute(text('CREATE DATABASE '+name))
    bind=create_engine(make_url(url).set(database=name),hide_parameters=True)
    yield bind
    # Retain test databases: no DROP DATABASE or persistent volume deletion.
    bind.dispose();admin.dispose()

def test_empty_startup_concurrent_and_existing_database_preserved(fresh_pg):
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _:initialize_empty_database(fresh_pg),range(3),timeout=60))
    with fresh_pg.begin() as con:
        assert con.scalar(text('SELECT version_num FROM alembic_version'))==HEAD
        con.execute(text("INSERT INTO users (username,password_hash) VALUES ('synthetic-existing','preserved')"))
    initialize_empty_database(fresh_pg)
    with fresh_pg.connect() as con:assert con.scalar(text("SELECT password_hash FROM users WHERE username='synthetic-existing'"))=='preserved'

def test_unknown_database_never_initialized(fresh_pg):
    with fresh_pg.begin() as con:con.execute(text('CREATE SEQUENCE unknown_object'))
    with pytest.raises(RuntimeError,match='未知对象'):initialize_empty_database(fresh_pg)
    assert inspect(fresh_pg).get_table_names()==[]

@pytest.fixture
def setup_client(fresh_pg,monkeypatch,tmp_path):
    import app.main as main
    import app.db as database
    from app.dependencies import db_dep
    from app.settings import Settings
    monkeypatch.setattr(main,'engine',fresh_pg);monkeypatch.setattr(database,'engine',fresh_pg)
    monkeypatch.setenv('SETUP_KEY','synthetic-key-'+secrets.token_hex(24))
    sf=sessionmaker(bind=fresh_pg)
    app=main.create_app(Settings(True,tmp_path/'media',True))
    def dependency():
        with sf() as db:yield db
    app.dependency_overrides[db_dep]=dependency
    from app.security import login_attempts
    login_attempts.clear()
    with TestClient(app,base_url='https://testserver') as c:yield c,sf
    login_attempts.clear()

def headers(c,authorized=True):
    return {'X-CSRF-Token':c.get('/api/auth/csrf').json()['csrf_token'],
            'Authorization':'Bearer '+(os.environ['SETUP_KEY'] if authorized else 'wrong')}

def payload():return {'username':'synthetic-owner','password':'QuietFox','title':'合成生活档案','subtitle':'合成副标题'}

def test_setup_authorization_transaction_defaults_password_and_repeat(setup_client):
    c,sf=setup_client
    assert c.get('/api/setup/status').json()=={'required':True}
    assert c.post('/api/setup/complete',json=payload()).status_code==403
    assert c.post('/api/setup/complete',json=payload(),headers=headers(c,False)).status_code==403
    assert c.post('/api/setup/complete',json={**payload(),'password':'12345678'},headers=headers(c)).status_code==422
    check=c.post('/api/setup/check',headers=headers(c));assert check.status_code==200,check.text
    assert check.json()['media_writable']
    r=c.post('/api/setup/complete',json=payload(),headers=headers(c));assert r.status_code==200,r.text
    assert c.get('/api/setup/status').json()=={'required':False}
    assert c.post('/api/setup/complete',json=payload(),headers=headers(c)).status_code==409
    assert c.post('/api/auth/login',json={'username':payload()['username'],'password':payload()['password']},headers=headers(c)).status_code==200
    assert c.get('/api/admin/system').status_code==200
    templates=c.get('/api/admin/templates').json();assert len(templates)==4
    assert c.get('/api/admin/content/types').status_code==200
    assert c.get('/api/journals').status_code==404
    assert c.get('/api/site/text').json()['values']['site.subtitle']=='合成副标题'
    from app.models import User
    with sf() as db:assert db.scalar(select(User)).password_hash!=payload()['password']


def test_setup_failure_rolls_back_everything_and_can_retry(setup_client,monkeypatch):
    c,sf=setup_client
    from app.services import templates
    original=templates.save_template
    def broken(*args,**kw):raise RuntimeError('synthetic-interruption')
    monkeypatch.setattr(templates,'save_template',broken)
    with pytest.raises(Exception):c.post('/api/setup/complete',json=payload(),headers=headers(c))
    from app.models import User
    with sf() as db:assert db.scalar(select(User.id)) is None
    monkeypatch.setattr(templates,'save_template',original)
    assert c.post('/api/setup/complete',json=payload(),headers=headers(c)).status_code==200


def test_concurrent_setup_one_winner_and_password_rotation(setup_client):
    c,sf=setup_client
    h=headers(c)
    def submit(_):return c.post('/api/setup/complete',json=payload(),headers=h).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,range(2),timeout=30))
    assert sorted(results)==[200,409]
    auth={'username':payload()['username'],'password':payload()['password']}
    assert c.post('/api/auth/login',json=auth,headers=h).status_code==200
    h=headers(c)
    assert c.post('/api/auth/password',json={'current_password':'wrong','new_password':'BetterFox'},headers=h).status_code==403
    assert c.post('/api/auth/password',json={'current_password':auth['password'],'new_password':'12345678'},headers=h).status_code==422
    assert c.post('/api/auth/password',json={'current_password':auth['password'],'new_password':'BetterFox'},headers=h).status_code==200
    assert c.get('/api/auth/me').status_code==401
    assert c.post('/api/auth/login',json={**auth,'password':'BetterFox'},headers=headers(c)).status_code==200


def test_text_allowlist_concurrency_and_ordinary_user_denied(setup_client):
    c,sf=setup_client
    assert c.get('/api/site/text').status_code==401
    assert c.post('/api/setup/complete',json=payload(),headers=headers(c)).status_code==200
    auth={'username':payload()['username'],'password':payload()['password']}
    assert c.post('/api/auth/login',json=auth,headers=headers(c)).status_code==200
    initial=c.get('/api/site/text').json()
    data={'expected_revision':initial['revision'],'values':{'admin.content':'我的生活','home.welcome':'<script>仅作为文字</script>'}}
    r=c.put('/api/admin/site/text',json=data,headers=headers(c));assert r.status_code==200,r.text
    assert c.put('/api/admin/site/text',json=data,headers=headers(c)).status_code==409
    assert c.put('/api/admin/site/text',json={'expected_revision':r.json()['revision'],'values':{'button.delete':'假冒安全按钮'}},headers=headers(c)).status_code==422
    from app.models import User
    from app.security import ph
    with sf() as db:db.add(User(username='synthetic-reader',password_hash=ph.hash('ReaderFox')));db.commit()
    c.post('/api/auth/logout',headers=headers(c))
    assert c.post('/api/auth/login',json={'username':'synthetic-reader','password':'ReaderFox'},headers=headers(c)).status_code==200
    assert c.get('/api/admin/system').status_code==403
    assert c.get('/api/site/text').status_code==403
    reading=c.get('/api/blog/site').json()['text']
    assert not any(k.startswith('admin.') for k in reading['values'])
    assert not any(k.startswith('admin.') for k in reading['defaults'])
    assert 'revision' not in reading and 'layout_revision' not in reading
    assert c.put('/api/admin/site/text',json=data,headers=headers(c)).status_code==403
    assert c.get('/api/admin/content/types').status_code==403


def test_unknown_function_is_not_an_empty_database(fresh_pg):
    with fresh_pg.begin() as con:
        con.execute(text("CREATE FUNCTION synthetic_unknown() RETURNS int LANGUAGE SQL AS 'SELECT 1'"))
    with pytest.raises(RuntimeError,match='未知对象'):initialize_empty_database(fresh_pg)
    assert inspect(fresh_pg).get_table_names()==[]


def test_display_text_and_layout_are_saved_atomically(setup_client):
    c,sf=setup_client
    assert c.post('/api/setup/complete',json=payload(),headers=headers(c)).status_code==200
    assert c.post('/api/auth/login',json={'username':payload()['username'],'password':payload()['password']},headers=headers(c)).status_code==200
    initial=c.get('/api/site/text').json()
    data={'expected_revision':initial['revision'],'title':'新的合成网站名','expected_layout_revision':initial['layout_revision'],'values':{'nav.home':'家'}}
    response=c.put('/api/admin/site/text',json=data,headers=headers(c));assert response.status_code==200
    saved=response.json();assert saved['site_name']=='新的合成网站名'
    conflict={**data,'expected_revision':saved['revision'],'values':{'nav.home':'不得保存'}}
    assert c.put('/api/admin/site/text',json=conflict,headers=headers(c)).status_code==409
    assert c.get('/api/site/text').json()['values']['nav.home']=='家'
    weak=c.post('/api/auth/password',json={'current_password':payload()['password'],'new_password':'password'},headers=headers(c))
    assert weak.status_code==422 and '"input"' not in weak.text


def test_failed_automatic_migration_rolls_back_schema(fresh_pg,monkeypatch):
    from app import migrations
    def interrupted(cfg,target):
        cfg.attributes['connection'].execute(text('CREATE TABLE synthetic_partial (id int)'))
        raise RuntimeError('synthetic migration interrupted')
    with monkeypatch.context() as patch:
        patch.setattr(migrations.command,'upgrade',interrupted)
        with pytest.raises(RuntimeError,match='interrupted'):initialize_empty_database(fresh_pg)
    assert inspect(fresh_pg).get_table_names()==[]
    initialize_empty_database(fresh_pg)
    assert 'admin_users' in inspect(fresh_pg).get_table_names()


def test_bootstrap_does_not_require_second_pool_connection(fresh_pg):
    single=create_engine(fresh_pg.url,pool_size=1,max_overflow=0,pool_timeout=1)
    try:
        initialize_empty_database(single)
        initialize_empty_database(single)
    finally:single.dispose()
