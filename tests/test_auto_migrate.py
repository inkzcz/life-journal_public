"""Gate tests use disposable PG17 databases. Real restore/tools run in Compose CI.
No test changes or deletes any pre-existing database, backup or media directory.
"""
import json
import multiprocessing
import os
import secrets
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from alembic import command
sys.path.insert(0, str(Path(__file__).parents[1]/'backend'))
os.environ.setdefault('DATABASE_URL','sqlite://')
from app import auto_migrate as gate, migrations
from app.services.write_barrier import writer
from fastapi import HTTPException

@pytest.fixture
def pg(tmp_path,monkeypatch):
    url=os.getenv('TEST_DATABASE_URL')
    if not url or make_url(url).get_backend_name()!='postgresql':pytest.skip('requires disposable PostgreSQL 17')
    admin=create_engine(url,isolation_level='AUTOCOMMIT')
    name='auto_gate_test_'+secrets.token_hex(6)
    with admin.connect() as con:con.execute(text('CREATE DATABASE '+name))
    bind=create_engine(make_url(url).set(database=name),hide_parameters=True)
    media=tmp_path/'media';media.mkdir();root=tmp_path/'backup';root.mkdir()
    monkeypatch.setenv('MEDIA_DIR',str(media));monkeypatch.setenv('BACKUP_ROOT',str(root));monkeypatch.setenv('LIFE_JOURNAL_VERSION','synthetic-auto-gate')
    yield bind,root,media
    bind.dispose();admin.dispose() # retain exact newly created test DB


def old_schema(bind):
    with bind.begin() as con:
        command.upgrade(migrations.config(con),'0016_markdown_travel')
        con.execute(text("INSERT INTO users(username,password_hash) VALUES ('synthetic-gate','preserved')"))
        con.execute(text("INSERT INTO journals(title,content,created_at,updated_at) VALUES ('synthetic','preserved',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))


def fake_validated_backup(monkeypatch):
    # Unit-only seam. Real pg_dump, isolated initdb/pg_restore and media copies
    # are mandatory in tests/auto_migration_compose.py release integration gate.
    monkeypatch.setattr(gate.shutil,'disk_usage',lambda _:SimpleNamespace(free=10**12))
    def bundle(bind,attempt,source):
        with pytest.raises(HTTPException) as e:
            with writer(bind):pass
        assert e.value.status_code==503
        with pytest.raises(gate.backup.BackupError):
            with gate.backup.backup_lock(exclusive=True):pass
        return {'tables':gate.fingerprint(bind)}
    monkeypatch.setattr(gate,'create_bundle',bundle)
    monkeypatch.setattr(gate,'restore_rehearsal',lambda *a:{'backup_restore':'passed'})


def test_only_reviewed_hash_pinned_linear_edge_is_automatic(monkeypatch):
    gate.approved('0015_travel_editing','0016_markdown_travel')
    gate.approved('0016_markdown_travel',migrations.HEAD)
    with pytest.raises(gate.GateError,match='未获'):gate.approved('0015_travel_editing',migrations.HEAD)
    with pytest.raises(gate.GateError,match='未获'):gate.approved('0014_place_identity',migrations.HEAD)
    monkeypatch.setattr(gate,'APPROVED',{('0016_markdown_travel',migrations.HEAD):{'0017_v5_organization.py':'0'*64}})
    with pytest.raises(gate.GateError,match='校验和'):gate.approved('0016_markdown_travel',migrations.HEAD)


def test_empty_and_repeated_startup_need_no_backup_or_ddl(pg,monkeypatch):
    bind,root,media=pg
    monkeypatch.setattr(gate,'create_bundle',lambda *a:pytest.fail('must not back up empty/current DB'))
    assert gate.run(bind)['state']=='initialized'
    with bind.begin() as con:con.execute(text("INSERT INTO users(username,password_hash) VALUES ('keep','preserve')"))
    before=gate.fingerprint(bind)
    assert gate.run(bind)['state']=='current'
    assert gate.run(bind)['state']=='current'
    assert gate.fingerprint(bind)==before and not list(root.iterdir())


def test_unknown_objects_and_unapproved_older_path_fail_closed(pg):
    bind,root,media=pg
    with bind.begin() as con:con.execute(text('CREATE SEQUENCE unknown_user_object'))
    with pytest.raises(RuntimeError,match='未知对象'):gate.run(bind)
    assert inspect(bind).get_table_names()==[]
    # Only the exact synthetic object made in this test is removed.
    with bind.begin() as con:con.execute(text('DROP SEQUENCE unknown_user_object'))
    with bind.begin() as con:command.upgrade(migrations.config(con),'0014_place_identity')
    before=gate.fingerprint(bind)
    with pytest.raises(gate.GateError,match='未获'):gate.run(bind)
    assert gate.fingerprint(bind)==before and not list(root.iterdir())


def test_missing_backup_target_blocks_original_upgrade(pg,monkeypatch):
    bind,root,media=pg;old_schema(bind);before=gate.fingerprint(bind)
    monkeypatch.setenv('BACKUP_ROOT',str(root/'not-mounted'))
    with pytest.raises(gate.backup.BackupError,match='不存在'):gate.run(bind)
    assert gate.schema(bind)=='0016_markdown_travel' and gate.fingerprint(bind)==before


def test_insufficient_space_never_changes_source(pg,monkeypatch):
    bind,root,media=pg;old_schema(bind);before=gate.fingerprint(bind)
    monkeypatch.setattr(gate.shutil,'disk_usage',lambda _:SimpleNamespace(free=0))
    with pytest.raises(gate.GateError,match='空间不足'):gate.run(bind)
    assert gate.fingerprint(bind)==before


def test_failed_restore_and_crash_receipt_block_retry_until_explicit_rearm(pg,monkeypatch):
    bind,root,media=pg;old_schema(bind);before=gate.fingerprint(bind)
    fake_validated_backup(monkeypatch);calls=[]
    def fail(*args):calls.append(1);raise RuntimeError('synthetic restore interruption')
    monkeypatch.setattr(gate,'restore_rehearsal',fail)
    with pytest.raises(RuntimeError,match='synthetic'):gate.run(bind)
    assert gate.fingerprint(bind)==before
    checkpoint=next(root.glob('.upgrades-v1/*/attempt.json'))
    assert json.loads(checkpoint.read_text())['state']=='running'
    with pytest.raises(gate.GateError,match='停止自动重试'):gate.run(bind)
    assert len(calls)==1
    with pytest.raises(RuntimeError,match='synthetic'):gate.run(bind,'GUI-reviewed-retry')
    assert len(calls)==2 and gate.fingerprint(bind)==before
    with pytest.raises(gate.GateError,match='停止自动重试'):gate.run(bind)
    assert len(calls)==2  # default/previous token is not a new GUI authorization


def test_migration_exception_rolls_back_schema_and_all_original_values(pg,monkeypatch):
    bind,root,media=pg;old_schema(bind);before=gate.fingerprint(bind)
    fake_validated_backup(monkeypatch);actual=gate.command.upgrade
    def fail(cfg,*args,**kw):
        actual(cfg,*args,**kw)
        raise RuntimeError('synthetic DDL interruption')
    monkeypatch.setattr(gate.command,'upgrade',fail)
    with pytest.raises(RuntimeError,match='interruption'):gate.run(bind)
    assert gate.schema(bind)=='0016_markdown_travel' and gate.fingerprint(bind)==before
    assert 'summary' in {c['name'] for c in inspect(bind).get_columns('content_records')}
    assert not (set(migrations.V5_TABLES) & set(inspect(bind).get_table_names()))


def test_original_value_preservation_check_is_inside_source_transaction(pg,monkeypatch):
    bind,root,media=pg;old_schema(bind);before=gate.fingerprint(bind)
    fake_validated_backup(monkeypatch);actual=gate.command.upgrade
    def changes_data(cfg,*args,**kw):
        actual(cfg,*args,**kw)
        cfg.attributes['connection'].execute(text("UPDATE journals SET content='must rollback'"))
    monkeypatch.setattr(gate.command,'upgrade',changes_data)
    with pytest.raises(gate.GateError,match='改变原值'):gate.run(bind)
    assert gate.schema(bind)=='0016_markdown_travel' and gate.fingerprint(bind)==before


def test_successful_upgrade_retains_old_values_and_next_startup_does_not_repeat(pg,monkeypatch):
    bind,root,media=pg;old_schema(bind);before=gate.fingerprint(bind);before.pop('alembic_version')
    fake_validated_backup(monkeypatch)
    result=gate.run(bind)
    assert result['state']=='upgraded'
    for table,expected in before.items():assert gate.fingerprint(bind)[table]==expected
    monkeypatch.setattr(gate,'create_bundle',lambda *a:pytest.fail('rebuild must not repeat backup/DDL'))
    assert gate.run(bind)['state']=='current'
    assert len(list(root.glob('.upgrades-v1/*/*/success.json')))==1


def lock_holder(url,event):
    bind=create_engine(url)
    with migrations.migration_lock(bind):
        event.set();event.wait(30)
        import time
        time.sleep(30)


def test_process_crash_releases_shared_migration_lock(pg):
    bind,root,media=pg;ctx=multiprocessing.get_context('spawn');ready=ctx.Event()
    child=ctx.Process(target=lock_holder,args=(bind.url.render_as_string(hide_password=False),ready))
    child.start()
    try:
        assert ready.wait(15)
        with bind.connect().execution_options(isolation_level='AUTOCOMMIT') as con:
            assert not con.scalar(text(f'SELECT pg_try_advisory_lock({migrations.MIGRATION_LOCK})'))
        child.terminate();child.join(10);assert not child.is_alive()
        with migrations.migration_lock(bind):pass
    finally:
        if child.is_alive():child.kill();child.join(5)


def test_old_heartbeat_cannot_bypass_local_startup_gate(pg,monkeypatch,tmp_path):
    from app import maintenance_health
    bind,root,media=pg;old_schema(bind)
    monkeypatch.setenv('AUTO_MIGRATE_ON_STARTUP','true')
    monkeypatch.setattr(maintenance_health,'engine',bind)
    monkeypatch.setattr(gate,'READY',tmp_path/'ready.json')
    with pytest.raises(SystemExit) as e:maintenance_health.main()
    assert e.value.code==1
    gate.atomic_json(gate.READY,{'schema':migrations.HEAD,'build':'synthetic-auto-gate'})
    with pytest.raises(SystemExit) as e:maintenance_health.main()
    assert e.value.code==1


def test_automatic_entrypoint_logs_never_echo_driver_credentials(monkeypatch,capsys,tmp_path):
    monkeypatch.setattr(gate,'READY',tmp_path/'ready.json')
    def fail(*a):raise RuntimeError('postgresql://private:DO_NOT_LOG@host/private_title')
    monkeypatch.setattr(gate,'run',fail)
    with pytest.raises(SystemExit) as e:gate.startup(None)
    assert e.value.code==1
    logs=capsys.readouterr().err
    assert 'DO_NOT_LOG' not in logs and 'private_title' not in logs and '安全停止' in logs


def test_old_schema_media_validation_never_loads_future_deferred_columns(pg,monkeypatch,capsys):
    from auto_migration_compose import SEED
    import app.db as database
    bind,root,media=pg
    monkeypatch.setattr(database,'engine',bind)
    exec(SEED.replace("'/data/media/library-v1'",repr(str(media/'library-v1'))),{})
    capsys.readouterr()
    gate.validate_media(bind,media)
    before=gate.fingerprint(bind)
    assert gate.schema(bind)=='0015_travel_editing'
    image=next(media.glob('library-v1/*/preview.webp'))
    image.write_bytes(b'synthetic corruption')
    with pytest.raises(Exception):gate.validate_media(bind,media)
    assert gate.fingerprint(bind)==before


def concurrent_upgrade_worker(url,results):
    # Only the external tool seam is stubbed; independent processes and all
    # source PostgreSQL locks, original-value checks and DDL are real.
    from types import SimpleNamespace
    bind=create_engine(url,hide_parameters=True)
    gate.shutil.disk_usage=lambda _:SimpleNamespace(free=10**12)
    gate.create_bundle=lambda b,*a:{'tables':gate.fingerprint(b)}
    gate.restore_rehearsal=lambda *a:{'backup_restore':'passed'}
    try:results.put(gate.run(bind)['state'])
    except Exception:results.put('failed')
    finally:bind.dispose()


def test_two_processes_only_one_performs_upgrade(pg):
    bind,root,media=pg;old_schema(bind)
    ctx=multiprocessing.get_context('spawn');results=ctx.Queue()
    children=[ctx.Process(target=concurrent_upgrade_worker,args=(bind.url.render_as_string(hide_password=False),results)) for _ in range(2)]
    try:
        for c in children:c.start()
        states=[results.get(timeout=30) for _ in children]
        for c in children:c.join(10)
        assert sorted(states)==['current','upgraded']
        assert all(not c.is_alive() and c.exitcode==0 for c in children)
        assert len(list(root.glob('.upgrades-v1/*/*/success.json')))==1
    finally:
        for c in children:
            if c.is_alive():c.kill();c.join(5)


def test_incomplete_and_tampered_bundles_are_never_restored(tmp_path,monkeypatch):
    bundle=tmp_path/'bundle';bundle.mkdir();(bundle/'media').mkdir();(bundle/'database.dump').write_bytes(b'synthetic-dump')
    manifest={'format':gate.FORMAT,'complete':True,'postgresql_major':17,'source_schema':'0016_markdown_travel','tables':{},'files':gate.backup.files(bundle)}
    gate.atomic_json(bundle/'manifest.json',manifest)
    assert gate.verify_bundle(bundle)['complete']
    (bundle/'database.dump').write_bytes(b'tampered')
    with pytest.raises(gate.GateError,match='不完整或校验失败'):gate.verify_bundle(bundle)
    manifest['complete']=False;gate.atomic_json(bundle/'manifest.json',manifest)
    with pytest.raises(gate.GateError):gate.verify_bundle(bundle)


def test_unversioned_development_can_bootstrap_but_cannot_claim_a_backup(monkeypatch,tmp_path):
    monkeypatch.setenv('LIFE_JOURNAL_VERSION','unversioned')
    monkeypatch.setattr(gate,'READY',tmp_path/'ready.json')
    monkeypatch.setattr(gate,'run',lambda *a:{'state':'current','schema':migrations.HEAD})
    gate.startup(None)
    assert json.loads(gate.READY.read_text())['build']=='unversioned'
    with pytest.raises(gate.backup.BackupError,match='版本未固定'):gate.backup.version()


def test_unknown_catalog_objects_in_old_database_block_automatic_upgrade(pg):
    bind,root,media=pg;old_schema(bind)
    for create,remove in [
        ('CREATE SCHEMA synthetic_extra','DROP SCHEMA synthetic_extra'),
        ('CREATE VIEW synthetic_extra AS SELECT 1 AS value','DROP VIEW synthetic_extra'),
        ("CREATE FUNCTION synthetic_extra() RETURNS int LANGUAGE SQL AS 'SELECT 1'",'DROP FUNCTION synthetic_extra()'),
    ]:
        with bind.begin() as con:con.execute(text(create))
        before=gate.fingerprint(bind)
        with pytest.raises(gate.GateError,match='自定义模式'):gate.run(bind)
        assert gate.fingerprint(bind)==before and not list(root.iterdir())
        # Remove only the exact empty synthetic object made immediately above.
        with bind.begin() as con:con.execute(text(remove))


def test_physical_backup_overlap_is_rejected_before_copying(tmp_path):
    media=tmp_path/'media';media.mkdir();backup=tmp_path/'backup';backup.mkdir()
    gate.require_disjoint_media(media,backup)
    with pytest.raises(gate.GateError,match='实际重叠'):gate.require_disjoint_media(media,media)
    nested=media/'nested-backup';nested.mkdir()
    with pytest.raises(gate.GateError,match='实际重叠'):gate.require_disjoint_media(media,nested)
    assert not list(nested.iterdir())
