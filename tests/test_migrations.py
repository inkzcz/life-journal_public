"""All writes target temporary SQLite files or newly created PostgreSQL test schemas.
TEST_DATABASE_URL must point only at a disposable testing database.
"""
import os
import secrets
import subprocess
import sys
from datetime import datetime, timedelta, timezone, date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text, event, MetaData, Table
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from alembic import command

sys.path.insert(0,str(Path(__file__).parents[1]/'backend'))
os.environ.setdefault('DATABASE_URL','sqlite://')
from app.migrations import CALENDAR_TABLES, ALBUM_TABLES, EXPERIENCE_TABLES, upgrade, require_current_schema, config, HEAD, PHASE1, DYNAMIC_TABLES, ARCHIVE_TABLES, BLOG_TABLES, TEMPLATE_TABLES, LIFE_TABLES, RECOVERY_TABLES, DISCOVERY_TABLES, WRITING_TABLES, FOLDER_TABLES, MEDIA_RECOVERY_TABLES, PLACE_TABLES, MARKDOWN_TABLES, V5_TABLES, EXCHANGE_TABLES
from app.legacy_schema import metadata as legacy


@pytest.fixture(params=['sqlite','postgresql'])
def migration_db(request,tmp_path):
    if request.param=='sqlite':
        bind=create_engine('sqlite:///'+str(tmp_path/'migration.db'))
        @event.listens_for(bind,'connect')
        def foreign_keys(connection,record):
            connection.execute('PRAGMA foreign_keys=ON')
        yield bind
        bind.dispose()
        return
    url=os.getenv('TEST_DATABASE_URL')
    if not url or make_url(url).get_backend_name()!='postgresql':
        pytest.skip('requires disposable PostgreSQL TEST_DATABASE_URL')
    admin=create_engine(url)
    schema='test_phase3a_'+secrets.token_hex(10)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
    scoped_url=make_url(url).update_query_dict({'options':'-csearch_path='+schema})
    bind=create_engine(scoped_url)
    try:
        yield bind
    finally:
        bind.dispose()
        # Only the exact schema created by this fixture is removed.
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


def seed_legacy(bind,phase1=False):
    tables=[legacy.tables[name] for name in sorted(PHASE1)] if phase1 else list(legacy.tables.values())
    legacy.create_all(bind,tables=tables)
    now=datetime(2026,1,1,20,30,tzinfo=timezone.utc)
    with bind.begin() as c:
        c.execute(legacy.tables['users'].insert().values(id=17,username='legacy-user',password_hash='synthetic-preserved-hash'))
        c.execute(legacy.tables['journals'].insert().values(id=21,title='虚构旧日记',content='# 原始 Markdown\n保留正文',created_at=now,updated_at=now))
        c.execute(legacy.tables['sessions'].insert().values(id=19,user_id=17,token_hash='a'*64,expires_at=now+timedelta(days=7)))
        c.execute(legacy.tables['media'].insert().values(id='00000000-0000-0000-0000-000000000021',journal_id=21,filename='synthetic.png',mime_type='image/png'))
        if not phase1:
            c.execute(legacy.tables['journal_metadata'].insert().values(journal_id=21,entry_date=date(2025,12,31),category='原分类'))
            c.execute(legacy.tables['journal_tags'].insert().values(journal_id=21,name='原标签'))


def snapshot(bind,names):
    with bind.connect() as c:
        return {name:[tuple(row) for row in c.execute(select(legacy.tables[name]).order_by(*legacy.tables[name].primary_key.columns))] for name in names}


def cli(bind,*args):
    env={**os.environ,'DATABASE_URL':bind.url.render_as_string(hide_password=False),
         'PYTHONPATH':str(Path(__file__).parents[1]/'backend')}
    return subprocess.run([sys.executable,'-m',*args],env=env,capture_output=True,text=True)


def test_fresh_database_upgrade_repeatability_and_model_match(migration_db):
    bind=migration_db
    upgrade(bind);upgrade(bind);require_current_schema(bind)
    assert set(inspect(bind).get_table_names())==set(legacy.tables)|{'admin_users','alembic_version'}|DYNAMIC_TABLES|ARCHIVE_TABLES|BLOG_TABLES|TEMPLATE_TABLES|LIFE_TABLES|RECOVERY_TABLES|DISCOVERY_TABLES|WRITING_TABLES|FOLDER_TABLES|MEDIA_RECOVERY_TABLES|PLACE_TABLES|MARKDOWN_TABLES|V5_TABLES|EXCHANGE_TABLES|EXPERIENCE_TABLES|ALBUM_TABLES|CALENDAR_TABLES
    with bind.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM users'))==0
        assert c.scalar(text('SELECT count(*) FROM admin_users'))==0
        command.check(config(c))


@pytest.mark.parametrize('phase1',[False,True])
def test_adoption_preserves_all_legacy_rows_schema_sequences_and_files(migration_db,tmp_path,phase1):
    bind=migration_db
    seed_legacy(bind,phase1)
    names=set(inspect(bind).get_table_names())
    before=snapshot(bind,names)
    before_columns={n:inspect(bind).get_columns(n) for n in names}
    photo=tmp_path/'00000000-0000-0000-0000-000000000021'
    photo.write_bytes(b'synthetic-original-photo-bytes')
    sequences={}
    if bind.dialect.name=='postgresql':
        with bind.connect() as c:
            sequences={name:tuple(c.execute(text(f'SELECT last_value,is_called FROM {name}_id_seq')).one()) for name in ['users','sessions','journals']}
    upgrade(bind);upgrade(bind);require_current_schema(bind)
    assert snapshot(bind,names)==before
    for name in names:
        assert [(c['name'],str(c['type']),c['nullable'],c.get('default')) for c in inspect(bind).get_columns(name)]==[(c['name'],str(c['type']),c['nullable'],c.get('default')) for c in before_columns[name]]
    assert photo.read_bytes()==b'synthetic-original-photo-bytes'
    with bind.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM admin_users'))==0
        if phase1:
            assert c.scalar(text('SELECT count(*) FROM journal_metadata'))==0
            assert c.scalar(text('SELECT count(*) FROM journal_tags'))==0
        for name,value in sequences.items():
            assert tuple(c.execute(text(f'SELECT last_value,is_called FROM {name}_id_seq')).one())==value


def test_drift_is_rejected_without_rewriting_old_data(migration_db):
    bind=migration_db;seed_legacy(bind)
    with bind.begin() as c:
        c.execute(text('ALTER TABLE journals ADD COLUMN unexpected TEXT'))
    before=snapshot(bind,legacy.tables)
    with pytest.raises(RuntimeError,match='结构不匹配'):
        upgrade(bind)
    assert snapshot(bind,legacy.tables)==before
    assert 'admin_users' not in inspect(bind).get_table_names()
    if bind.dialect.name=='postgresql':
        assert 'alembic_version' not in inspect(bind).get_table_names()


def test_partial_and_unknown_schemas_are_not_blindly_adopted(migration_db):
    bind=migration_db
    with bind.begin() as c:
        c.execute(text('CREATE TABLE journals (id INTEGER PRIMARY KEY, title TEXT)'))
        c.execute(text("INSERT INTO journals VALUES (1,'preserve')"))
    with pytest.raises(RuntimeError,match='停止升级'):
        upgrade(bind)
    with bind.connect() as c:
        assert c.execute(text('SELECT * FROM journals')).all()==[(1,'preserve')]
    assert 'users' not in inspect(bind).get_table_names()


def test_missing_required_legacy_index_is_rejected(migration_db):
    bind=migration_db;seed_legacy(bind)
    with bind.begin() as c:
        c.execute(text('DROP INDEX ix_media_journal_id'))
    with pytest.raises(RuntimeError,match='索引'):
        upgrade(bind)
    assert 'admin_users' not in inspect(bind).get_table_names()


def test_downgrade_is_blocked_and_keeps_authorization_data(migration_db):
    bind=migration_db;seed_legacy(bind);upgrade(bind)
    with bind.begin() as c:
        c.execute(text('INSERT INTO admin_users(user_id) VALUES (17)'))
    before=snapshot(bind,legacy.tables)
    with pytest.raises(RuntimeError,match='禁止删除纪念日和提醒发送记录'):
        with bind.begin() as c:
            command.downgrade(config(c),'base')
    require_current_schema(bind)
    assert snapshot(bind,legacy.tables)==before
    with bind.connect() as c:
        assert c.scalar(text('SELECT user_id FROM admin_users'))==17
        assert c.scalar(text('SELECT version_num FROM alembic_version'))==HEAD


def test_import_and_unmigrated_startup_never_create_schema(migration_db,tmp_path):
    bind=migration_db
    env={**os.environ,'DATABASE_URL':bind.url.render_as_string(hide_password=False),
         'MEDIA_DIR':str(tmp_path/'untouched'), 'PYTHONPATH':str(Path(__file__).parents[1]/'backend')}
    script='''from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.db import engine
from sqlalchemy import inspect
assert inspect(engine).get_table_names()==[]
assert not app.state.settings.media_dir.exists()
try:
    with TestClient(app):
        pass
except RuntimeError as exc:
    assert ('未知对象' if engine.dialect.name=='postgresql' else '数据库未初始化') in str(exc)
else:
    raise AssertionError('Unmigrated startup must fail closed')
assert inspect(engine).get_table_names()==[]
'''
    result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_cli_upgrade_check_and_grant_are_explicit_and_repeatable(migration_db):
    bind=migration_db;seed_legacy(bind)
    assert cli(bind,'app.migrate','check').returncode!=0
    for _ in range(2):
        result=cli(bind,'app.migrate','upgrade')
        assert result.returncode==0,result.stderr
        assert cli(bind,'app.migrate','check').returncode==0
    before=snapshot(bind,legacy.tables)
    for _ in range(2):
        result=cli(bind,'app.manage_admin','grant','legacy-user')
        assert result.returncode==0,result.stderr
    assert snapshot(bind,legacy.tables)==before
    with bind.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM admin_users'))==1
    assert cli(bind,'app.manage_admin','grant','missing-user').returncode!=0
    result=cli(bind,'app.create_admin')
    assert result.returncode!=0 and '管理员已存在' in result.stderr


def test_new_admin_creation_is_atomic_and_granted(migration_db,monkeypatch):
    import app.create_admin as create
    bind=migration_db;upgrade(bind)
    monkeypatch.setattr(create,'engine',bind)
    monkeypatch.setattr(create,'SessionLocal',sessionmaker(bind=bind))
    monkeypatch.setattr('builtins.input',lambda _: 'fresh-admin')
    monkeypatch.setattr(create.getpass,'getpass',lambda _: secrets.token_urlsafe(24))
    create.main()
    with bind.connect() as c:
        uid=c.scalar(text("SELECT id FROM users WHERE username='fresh-admin'"))
        assert c.scalar(text('SELECT user_id FROM admin_users'))==uid
    with pytest.raises(SystemExit,match='管理员已存在'):
        create.main()


def test_unknown_revision_is_rejected(migration_db):
    bind=migration_db;upgrade(bind)
    with bind.begin() as c:
        c.execute(text("UPDATE alembic_version SET version_num='unknown_future_revision'"))
    with pytest.raises(RuntimeError,match='数据库版本不兼容'):
        require_current_schema(bind)


def test_preflight_is_read_only(migration_db):
    from app.migrations import preflight
    bind=migration_db
    assert preflight(bind)=='empty'
    assert inspect(bind).get_table_names()==[]
    seed_legacy(bind)
    before=snapshot(bind,legacy.tables)
    assert preflight(bind)=='phase2'
    assert cli(bind,'app.migrate','preflight').returncode==0
    assert set(inspect(bind).get_table_names())==set(legacy.tables)
    assert snapshot(bind,legacy.tables)==before
    upgrade(bind)
    assert preflight(bind)=='current'


def test_postgresql_concurrent_upgrades_are_serialized(migration_db):
    bind=migration_db
    if bind.dialect.name!='postgresql':
        pytest.skip('PostgreSQL advisory-lock behavior only')
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda _: cli(bind,'app.migrate','upgrade'),range(2)))
    assert all(result.returncode==0 for result in results),[r.stderr for r in results]
    require_current_schema(bind)


def test_existing_session_and_photo_remain_usable_after_upgrade(migration_db,tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from app.security import digest
    from app.settings import Settings
    from app.dependencies import db_dep
    import app.main as main
    bind=migration_db;seed_legacy(bind)
    token=secrets.token_urlsafe(32)
    with bind.begin() as c:
        c.execute(legacy.tables['sessions'].update().values(token_hash=digest(token),expires_at=datetime.now(timezone.utc)+timedelta(days=7)))
    photo=tmp_path/'00000000-0000-0000-0000-000000000021';photo.write_bytes(b'original-file')
    before=snapshot(bind,legacy.tables)
    upgrade(bind)
    monkeypatch.setattr(main,'engine',bind)
    app=main.create_app(Settings(True,tmp_path,False))
    from legacy_backend import journals,media
    app.include_router(journals.router);app.include_router(media.router)  # archival read verification only
    factory=sessionmaker(bind=bind)
    def test_db():
        with factory() as db:
            yield db
    app.dependency_overrides[db_dep]=test_db
    with TestClient(app,base_url='https://testserver') as client:
        client.cookies.set('life_session',token)
        assert client.get('/api/auth/me').json()=={'username':'legacy-user'}
        assert client.get('/api/journals/21').json()['content']=='# 原始 Markdown\n保留正文'
        assert client.get('/api/media/'+photo.name).content==b'original-file'
        assert client.get('/api/admin/status').status_code==403
    assert snapshot(bind,legacy.tables)==before


def test_admin_foreign_key_protects_existing_user(migration_db):
    from sqlalchemy.exc import IntegrityError
    bind=migration_db;seed_legacy(bind);upgrade(bind)
    with bind.begin() as c:
        c.execute(text('INSERT INTO admin_users(user_id) VALUES (17)'))
    with pytest.raises(IntegrityError):
        with bind.begin() as c:
            c.execute(text('DELETE FROM users WHERE id=17'))
    with bind.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM users WHERE id=17'))==1
        assert c.scalar(text('SELECT count(*) FROM admin_users WHERE user_id=17'))==1


def test_failed_admin_creation_rolls_back_user_and_grant(migration_db,monkeypatch):
    import app.create_admin as create
    from sqlalchemy.orm import Session as DBSession
    bind=migration_db;upgrade(bind)
    class FailedCommit(DBSession):
        def commit(self):
            raise RuntimeError('synthetic commit failure')
    monkeypatch.setattr(create,'engine',bind)
    monkeypatch.setattr(create,'SessionLocal',sessionmaker(bind=bind,class_=FailedCommit))
    monkeypatch.setattr('builtins.input',lambda _: 'failed-admin')
    monkeypatch.setattr(create.getpass,'getpass',lambda _: secrets.token_urlsafe(24))
    with pytest.raises(RuntimeError,match='synthetic commit failure'):
        create.main()
    with bind.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM users'))==0
        assert c.scalar(text('SELECT count(*) FROM admin_users'))==0


def test_phase3a_to_phase3b_additive_upgrade(migration_db):
    bind=migration_db
    seed_legacy(bind)
    with bind.begin() as c:
        # Explicitly construct the released Phase 3A schema before upgrading.
        command.stamp(config(c),'0001_legacy')
        command.upgrade(config(c),'0002_admin_users')
        c.execute(text('INSERT INTO admin_users (user_id, granted_at) VALUES (17, CURRENT_TIMESTAMP)'))
    before=snapshot(bind,set(legacy.tables))
    upgrade(bind);upgrade(bind)
    assert snapshot(bind,set(legacy.tables))==before
    with bind.connect() as c:
        assert c.scalar(text('SELECT user_id FROM admin_users'))==17
        assert c.scalar(text('SELECT count(*) FROM content_records'))==0
        assert c.scalar(text('SELECT version_num FROM alembic_version'))==HEAD
        with pytest.raises(RuntimeError,match='禁止删除纪念日和提醒发送记录'):
            command.downgrade(config(c),'0002_admin_users')
    require_current_schema(bind)


def test_phase3b_upgrade_preserves_dynamic_data_and_legacy_media(migration_db,tmp_path):
    from sqlalchemy.orm import Session
    from app.content_models import ContentType,ContentTypeVersion,FieldDefinition,VersionField,ContentRecord,RecordRevision
    from app.models import User,AdminUser
    from app.migrations import preflight
    import uuid
    bind=migration_db
    with bind.begin() as c:command.upgrade(config(c),'0003_dynamic_content')
    tid,fid,rid=[str(uuid.uuid4()) for _ in range(3)]
    with Session(bind) as db:
        user=User(username='synthetic-3b',password_hash='synthetic');db.add(user);db.flush();db.add(AdminUser(user_id=user.id))
        db.add(ContentType(id=tid,slug='synthetic-model',name='旧动态类型'));db.flush()
        db.add(ContentTypeVersion(type_id=tid,number=1,created_by=user.id));db.add(FieldDefinition(id=fid,type_id=tid,kind='short_text'));db.flush()
        db.add(VersionField(type_id=tid,version=1,field_id=fid,name='历史字段',position=0));db.flush()
        db.add(ContentRecord(id=rid,type_id=tid,schema_version=1,title='虚构旧动态记录',body='# 保留正文',display_date=date(2026,1,1),values={fid:'保留值'}));db.flush()
        db.add(RecordRevision(record_id=rid,number=1,actor_id=user.id,snapshot={'values':{fid:'保留值'}}));db.commit()
    photo=tmp_path/'old-photo';photo.write_bytes(b'synthetic unchanged photo')
    # Compare every original column, not newly added metadata columns.
    baseline_tables=MetaData()
    baseline_tables.reflect(bind,only=list(DYNAMIC_TABLES|{'users','admin_users'}))
    def dynamic_snapshot():
        with bind.connect() as c:return {name:[tuple(row) for row in c.execute(select(baseline_tables.tables[name]))] for name in DYNAMIC_TABLES|{'users','admin_users'}}
    before=dynamic_snapshot();assert preflight(bind)=='phase3b'
    upgrade(bind);upgrade(bind);require_current_schema(bind)
    assert dynamic_snapshot()==before and photo.read_bytes()==b'synthetic unchanged photo'
    with bind.connect() as c:
        assert all(c.scalar(text('SELECT count(*) FROM '+name))==0 for name in ARCHIVE_TABLES)
        command.check(config(c))


def test_phase3c_to_phase3d_preserves_every_existing_row(migration_db,tmp_path):
    from sqlalchemy.orm import Session
    from app import archive_models,content_models,blog_models
    from app.db import Base
    from app.migrations import preflight
    from app.archive_models import MediaAsset,Place,RecordMedia,RecordLink,RecordPlace
    from app.content_models import ContentType,ContentTypeVersion,ContentRecord
    import uuid
    bind=migration_db;seed_legacy(bind)
    with bind.begin() as c:
        command.stamp(config(c),'0001_legacy');command.upgrade(config(c),'0004_archive_resources')
    tid,a,b,mid,pid=[str(uuid.uuid4()) for _ in range(5)]
    with Session(bind) as db:
        db.add(ContentType(id=tid,slug='preserved-3c',name='虚构旧类型'));db.flush()
        db.add(ContentTypeVersion(type_id=tid,number=1,created_by=17));db.flush()
        for rid in [a,b]:db.add(ContentRecord(id=rid,type_id=tid,schema_version=1,title='虚构旧记录',display_date=date(2026,1,1),values={}))
        db.add(MediaAsset(id=mid,filename='synthetic.jpg',mime_type='image/jpeg',size=10,width=2,height=2,sha256='a'*64,preview_sha256='b'*64,uploaded_by=17));db.add(Place(id=pid,name='虚构旧地点'));db.flush()
        db.add(RecordMedia(record_id=a,media_id=mid,position=0,cover=True));db.add(RecordLink(source_id=a,target_id=b,label='旧关系'));db.add(RecordPlace(record_id=a,place_id=pid));db.commit()
    names=set(inspect(bind).get_table_names())-{'alembic_version'}
    # Freeze the released schema's columns; current ORM includes later additive columns.
    released=MetaData();tables={n:Table(n,released,autoload_with=bind) for n in names}
    def before_after():
        with bind.connect() as c:return {n:[tuple(r) for r in c.execute(select(tables[n]).order_by(*tables[n].primary_key.columns))] for n in names}
    before=before_after();photo=tmp_path/'original';photo.write_bytes(b'synthetic-original')
    assert preflight(bind)=='phase3c';upgrade(bind);upgrade(bind);require_current_schema(bind)
    assert before_after()==before and photo.read_bytes()==b'synthetic-original'
    with bind.connect() as c:
        assert all(c.scalar(text('SELECT count(*) FROM '+n))==0 for n in BLOG_TABLES)
        command.check(config(c))


def test_fresh_blog_defaults_are_read_only_and_empty(migration_db):
    from sqlalchemy.orm import Session
    from app.services.blog import home,config_data
    bind=migration_db;upgrade(bind)
    with Session(bind) as db:
        data=home(db)
        assert [m['kind'] for m in data['modules']]==['hero','latest']
        assert all(m['items']==[] for m in data['modules'])
        assert config_data(db,'appearance')=={'theme':'modern','mode':'system','revision':0}
        assert db.scalar(text('SELECT count(*) FROM site_configs'))==0
        assert db.scalar(text('SELECT count(*) FROM content_records'))==0


def test_phase3d_to_phase3e_preserves_all_rows_and_files(migration_db,tmp_path):
    from sqlalchemy.orm import Session
    from app import template_models,blog_models,archive_models,content_models
    from app.db import Base
    from app.blog_models import Section,NavigationItem,SiteConfig
    from app.content_models import ContentType,ContentTypeVersion,ContentRecord
    from app.archive_models import MediaAsset,RecordMedia,Place,RecordPlace
    from app.migrations import preflight
    import uuid
    bind=migration_db;seed_legacy(bind)
    with bind.begin() as c:
        command.stamp(config(c),'0001_legacy');command.upgrade(config(c),'0005_blog_presentation')
    tid,rid,mid,pid,sid,nid=[str(uuid.uuid4()) for _ in range(6)]
    with Session(bind) as db:
        db.add(ContentType(id=tid,slug='preserved-3d',name='原有动态类型'));db.flush()
        db.add(ContentTypeVersion(type_id=tid,number=1,created_by=17));db.flush()
        db.add(ContentRecord(id=rid,type_id=tid,schema_version=1,title='原有文章',body='# 原正文',display_date=date(2026,1,1),status='published',values={}));db.flush()
        db.add(MediaAsset(id=mid,filename='original.jpg',mime_type='image/jpeg',size=10,width=2,height=2,sha256='c'*64,preview_sha256='d'*64,uploaded_by=17));db.add(Place(id=pid,name='原地点'));db.flush()
        db.add(RecordMedia(record_id=rid,media_id=mid,position=0,cover=True));db.add(RecordPlace(record_id=rid,place_id=pid))
        db.add(Section(id=sid,name='原栏目',slug='original-section',cover_id=mid));db.flush()
        db.add(NavigationItem(id=nid,name='原导航',kind='record',record_id=rid,position=0))
        db.add(SiteConfig(id=str(uuid.uuid4()),key='appearance',value={'theme':'glass','mode':'dark'},revision=8));db.commit()
    names=set(inspect(bind).get_table_names())-{'alembic_version'}
    # Freeze the released schema's columns; current ORM includes later additive columns.
    released=MetaData();tables={n:Table(n,released,autoload_with=bind) for n in names}
    def rows():
        with bind.connect() as c:return {n:[tuple(r) for r in c.execute(select(tables[n]).order_by(*tables[n].primary_key.columns))] for n in names}
    before=rows();photo=tmp_path/'synthetic-private-photo';photo.write_bytes(b'preserve original bytes')
    assert preflight(bind)=='phase3d'
    with pytest.raises(RuntimeError):require_current_schema(bind)
    upgrade(bind);upgrade(bind);require_current_schema(bind)
    assert rows()==before and photo.read_bytes()==b'preserve original bytes'
    with bind.connect() as c:
        assert all(c.scalar(text('SELECT count(*) FROM '+name))==0 for name in TEMPLATE_TABLES)
        command.check(config(c))
    with pytest.raises(RuntimeError,match='禁止删除纪念日和提醒发送记录'):
        with bind.begin() as c:command.downgrade(config(c),'0005_blog_presentation')
    require_current_schema(bind)


def test_phase3e_to_phase3f_preserves_template_bindings_and_all_rows(migration_db,tmp_path):
    import uuid
    from sqlalchemy.orm import Session
    from app.db import Base
    from app.template_presets import presets
    from app.template_schemas import TemplateIn
    from app.services.templates import save_template
    from app.template_models import RecordTemplate,TemplateVersion
    from app.content_models import ContentRecord,RecordRevision
    from app.migrations import preflight
    bind=migration_db;seed_legacy(bind)
    with bind.begin() as c:
        command.stamp(config(c),'0001_legacy');command.upgrade(config(c),'0006_content_templates')
    with Session(bind) as db:
        data=presets()[0];data.pop('key');data['modules']=[m for m in data['modules'] if m['kind'] not in {'itinerary','map'}];t=save_template(db,TemplateIn(**data),17)
        version=db.get(TemplateVersion,(t.id,1));version.config={**version.config,'modules':[{k:v for k,v in m.items() if k!='group_by'} for m in version.config['modules']]}
        r=ContentRecord(id=str(uuid.uuid4()),type_id=t.type_id,schema_version=1,title='原模板文章',body='# 保留内容',display_date=date(2026,1,1),status='published',values={})
        db.add(r);db.flush();db.add(RecordTemplate(record_id=r.id,template_id=t.id,version=1));db.add(RecordRevision(record_id=r.id,number=1,snapshot={'title':r.title,'template_version':1},actor_id=17));rid=r.id;db.commit()
    names=set(inspect(bind).get_table_names())-{'alembic_version'}
    # Freeze the released schema's columns; current ORM includes later additive columns.
    released=MetaData();tables={n:Table(n,released,autoload_with=bind) for n in names}
    def rows():
        with bind.connect() as c:return {n:[tuple(r) for r in c.execute(select(tables[n]).order_by(*tables[n].primary_key.columns))] for n in names}
    before=rows();photo=tmp_path/'synthetic-original';photo.write_bytes(b'unchanged-private-media')
    assert preflight(bind)=='phase3e'
    upgrade(bind);upgrade(bind);require_current_schema(bind)
    assert rows()==before and photo.read_bytes()==b'unchanged-private-media'
    from app.services.blog import detail
    with Session(bind) as db:
        restored=detail(db,db.get(ContentRecord,rid));assert restored['template']['version']==1 and restored['life']['activities']==[]
        assert all('group_by' not in m for m in restored['template']['config']['modules'])
    with bind.connect() as c:
        assert all(c.scalar(text('SELECT count(*) FROM '+n))==0 for n in LIFE_TABLES)
        command.check(config(c))
    with pytest.raises(RuntimeError,match='禁止删除纪念日和提醒发送记录'):
        with bind.begin() as c:command.downgrade(config(c),'0006_content_templates')


def test_phase3g_to_3h_preserves_trash_revisions_life_and_colors(migration_db,tmp_path):
    import uuid
    from sqlalchemy.orm import Session
    from app.db import Base
    from app.content_models import ContentType,ContentTypeVersion,ContentRecord,RecordRevision
    from app.life_models import TripPlan,TripActivity
    from app.blog_models import SiteConfig
    from app.migrations import preflight
    bind=migration_db;seed_legacy(bind)
    with bind.begin() as c:
        command.stamp(config(c),'0001_legacy');command.upgrade(config(c),'0007_life_archive')
    with Session(bind) as db:
        t=ContentType(id=str(uuid.uuid4()),slug='preserved-3g',name='旧类型');db.add(t);db.flush()
        db.add(ContentTypeVersion(type_id=t.id,number=1,created_by=17));db.flush()
        r=ContentRecord(id=str(uuid.uuid4()),type_id=t.id,schema_version=1,title='旧回收站文章',body='保留正文',display_date=date(2026,1,1),deleted_at=datetime.now(timezone.utc));db.add(r);db.flush()
        db.add(RecordRevision(record_id=r.id,number=1,snapshot={'title':'原历史'},actor_id=17))
        db.add(TripPlan(record_id=r.id,map_mode='offline'))
        db.add(TripActivity(id=str(uuid.uuid4()),record_id=r.id,day=date(2026,1,1),title='旧行程',position=0))
        db.add(SiteConfig(id=str(uuid.uuid4()),key='appearance',value={'theme':'glass','mode':'system','colors':{'glass':{'dark':{'heading_text':'#eeddcc'}}}},revision=9));db.commit()
    names=set(inspect(bind).get_table_names())-{'alembic_version'}
    # Freeze the released schema's columns; current ORM includes later additive columns.
    released=MetaData();tables={n:Table(n,released,autoload_with=bind) for n in names}
    def rows():
        with bind.connect() as c:return {n:[tuple(r) for r in c.execute(select(tables[n]).order_by(*tables[n].primary_key.columns))] for n in names}
    before=rows();photo=tmp_path/'original';photo.write_bytes(b'synthetic-private-original')
    assert preflight(bind)=='phase3f'
    upgrade(bind);upgrade(bind);require_current_schema(bind)
    assert rows()==before and photo.read_bytes()==b'synthetic-private-original'
    with bind.connect() as c:
        assert all(c.scalar(text('SELECT count(*) FROM '+n))==0 for n in RECOVERY_TABLES)
        command.check(config(c))


def test_phase3k_to_3l_shared_tags_preserves_legacy_and_all_rows(migration_db):
    from app.migrations import preflight
    from sqlalchemy import MetaData,Table
    bind=migration_db;seed_legacy(bind)
    with bind.begin() as c:
        command.stamp(config(c),'0001_legacy');command.upgrade(config(c),'0008_recovery')
        # Same journal may contain differently spelled labels. Mapping never erases either.
        c.execute(text("INSERT INTO journal_tags(journal_id,name) VALUES(21,'ＡＢＣ'),(21,'abc'),(21,'繁體中文')"))
    names=set(inspect(bind).get_table_names())-{'alembic_version'}
    metadata=MetaData();tables={n:Table(n,metadata,autoload_with=bind) for n in names}
    def rows():
        with bind.connect() as c:return {n:[tuple(r) for r in c.execute(select(t).order_by(*t.primary_key.columns))] for n,t in tables.items()}
    before=rows();assert preflight(bind)=='phase3h'
    upgrade(bind);upgrade(bind);require_current_schema(bind)
    assert rows()==before
    with bind.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM journal_tag_identities'))==4
        assert c.scalar(text('SELECT count(*) FROM tags'))==3
        assert c.scalar(text("SELECT count(DISTINCT tag_id) FROM journal_tag_identities WHERE name IN ('ＡＢＣ','abc')"))==1
        assert c.scalar(text('SELECT count(*) FROM record_tags'))==0
        command.check(config(c))


def test_phase3l_to_3m_adds_only_nullable_media_metadata_and_order_index(migration_db,tmp_path):
    from app.migrations import preflight
    bind=migration_db;seed_legacy(bind)
    with bind.begin() as c:
        command.stamp(config(c),'0001_legacy');command.upgrade(config(c),'0009_archive_discovery')
        # Freeze exactly the released columns, not current ORM defaults.
        old=MetaData();media=Table('media_assets',old,autoload_with=c)
        import uuid
        mid=str(uuid.uuid4())
        c.execute(media.insert().values(id=mid,filename='synthetic-preserved.jpg',mime_type='image/jpeg',size=20,width=2000,height=1000,sha256='a'*64,preview_sha256='b'*64,title='原图标题',description='原说明',alt='原替代文本',uploaded_by=17,created_at=datetime.now(timezone.utc),revision=7))
    names=set(inspect(bind).get_table_names())-{'alembic_version'};released=MetaData();tables={n:Table(n,released,autoload_with=bind) for n in names}
    def rows():
        with bind.connect() as c:return {n:[tuple(r) for r in c.execute(select(t).order_by(*t.primary_key.columns))] for n,t in tables.items()}
    before=rows();original=tmp_path/'original';original.write_bytes(b'synthetic-original-unchanged')
    assert preflight(bind)=='phase3l';upgrade(bind);upgrade(bind);require_current_schema(bind)
    assert rows()==before and original.read_bytes()==b'synthetic-original-unchanged'
    with bind.connect() as c:
        assert tuple(c.execute(text('SELECT preview_width,preview_height,thumbnail_sha256 FROM media_assets')).one())==(None,None,None)
        command.check(config(c))
    assert 'ix_records_active_order' in {i['name'] for i in inspect(bind).get_indexes('content_records')}


def test_v410_to_v420_preserves_all_original_columns_and_files(migration_db,tmp_path):
    bind=migration_db;seed_legacy(bind)
    with bind.begin() as c:
        command.stamp(config(c),'0001_legacy');command.upgrade(config(c),'0015_travel_editing')
    # Freeze released columns so added nullable/default metadata cannot disguise changes.
    metadata=MetaData();tables={n:Table(n,metadata,autoload_with=bind) for n in inspect(bind).get_table_names() if n!='alembic_version'}
    def rows():
        with bind.connect() as c:return {n:[tuple(r) for r in c.execute(select(t).order_by(*t.primary_key.columns))] for n,t in tables.items()}
    original=rows();photo=tmp_path/'synthetic-original.jpg';photo.write_bytes(b'unchanged synthetic original')
    upgrade(bind);upgrade(bind);require_current_schema(bind)
    assert rows()==original and photo.read_bytes()==b'unchanged synthetic original'
    with bind.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM record_marked_places'))==0
        command.check(config(c))
    with pytest.raises(RuntimeError,match='禁止删除纪念日和提醒发送记录'):
        with bind.begin() as c:command.downgrade(config(c),'0015_travel_editing')
    assert rows()==original
    require_current_schema(bind)
