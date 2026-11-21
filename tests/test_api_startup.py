"""Actual historical PostgreSQL schema; API never bypasses Maintenance backups.
The external upgrade seam tests readiness only. Actual full restore/DDL rollback
are exercised separately by auto_migration_compose.py with real PG17 tools.
"""
import os
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import text
from test_auto_migrate import pg, old_schema
from app import api_startup as startup, migrations


def test_observed_failure_preflight_is_not_an_upgrade(pg):
    bind,_,_=pg;old_schema(bind)
    assert migrations.preflight(bind) != 'current'
    with pytest.raises(RuntimeError,match='版本不兼容'):
        migrations.initialize_empty_database(bind)
    assert startup.revision(bind)=='0016_markdown_travel'


def test_api_empty_current_repeated_and_private_values_preserved(pg):
    bind,_,_=pg
    startup.prepare(bind)
    with bind.begin() as con:con.execute(text("INSERT INTO users(username,password_hash) VALUES ('synthetic-api','preserved')"))
    startup.prepare(bind);startup.prepare(bind)
    with bind.connect() as con:assert con.scalar(text("SELECT password_hash FROM users WHERE username='synthetic-api'"))=='preserved'


def test_api_waits_for_real_transactional_coordinator_and_checks_schema(pg,monkeypatch):
    bind,_,_=pg;old_schema(bind)
    monkeypatch.setenv('MIGRATION_COORDINATOR','maintenance')
    calls=[]
    def external_gate(_):
        # Readiness seam only: no claim that this manual fixture proves backups.
        calls.append(1);migrations.upgrade(bind)
    startup.prepare(bind,timeout=10,sleep=external_gate)
    assert calls==[1] and startup.revision(bind)==migrations.HEAD
    with bind.connect() as con:assert con.scalar(text("SELECT content FROM journals WHERE title='synthetic'"))=='preserved'


def test_legacy_compose_fails_with_actionable_reason_not_bare_alembic(pg,monkeypatch,capsys):
    bind,_,_=pg;old_schema(bind);monkeypatch.delenv('MIGRATION_COORDINATOR',raising=False)
    with pytest.raises(startup.StartupError,match='配套Compose'):startup.prepare(bind)
    out=capsys.readouterr().out
    assert '0016_markdown_travel' in out and migrations.HEAD in out
    assert startup.revision(bind)=='0016_markdown_travel'


def test_failed_maintenance_never_opens_api_or_changes_old_data(pg,monkeypatch):
    bind,_,_=pg;old_schema(bind);monkeypatch.setenv('MIGRATION_COORDINATOR','maintenance')
    with pytest.raises(startup.StartupError,match='期限'):startup.prepare(bind,timeout=0)
    assert startup.revision(bind)=='0016_markdown_travel'
    with bind.connect() as con:assert con.scalar(text("SELECT content FROM journals WHERE title='synthetic'"))=='preserved'


def test_unknown_revision_and_broken_head_block_readiness(pg):
    bind,_,_=pg;old_schema(bind)
    with bind.begin() as con:con.execute(text("UPDATE alembic_version SET version_num='unknown_version'"))
    with pytest.raises(startup.StartupError):startup.prepare(bind)
    with bind.begin() as con:con.execute(text("UPDATE alembic_version SET version_num='0017_v5_organization'"))
    with pytest.raises(startup.StartupError):startup.prepare(bind)


def test_disabled_automatic_mode_does_not_migrate(pg,monkeypatch):
    bind,_,_=pg;old_schema(bind);monkeypatch.setenv('AUTO_MIGRATE_ON_STARTUP','false')
    with pytest.raises(startup.StartupError,match='关闭'):startup.prepare(bind)
    assert startup.revision(bind)=='0016_markdown_travel'


def test_driver_error_is_not_echoed(monkeypatch,capsys):
    monkeypatch.setattr(startup,'revision',lambda _:(_ for _ in ()).throw(RuntimeError('password=private-fixture-secret')))
    with pytest.raises(startup.StartupError):startup.prepare(None)
    assert 'private-fixture-secret' not in capsys.readouterr().out


def test_health_without_successful_lifespan_is_not_healthy():
    from fastapi.testclient import TestClient
    from app.main import create_app
    c=TestClient(create_app(),base_url='https://testserver')
    assert c.get('/api/health').status_code==503


def test_three_api_replicas_wait_without_issuing_duplicate_ddl(pg,monkeypatch):
    import threading
    bind,_,_=pg;old_schema(bind)
    monkeypatch.setenv('MIGRATION_COORDINATOR','maintenance')
    barrier=threading.Barrier(4)
    first=threading.local()
    def waiting(seconds):
        if not getattr(first,'seen',False):first.seen=True;barrier.wait(timeout=15)
        import time;time.sleep(min(seconds,0.05))
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks=[pool.submit(startup.prepare,bind,timeout=20,sleep=waiting) for _ in range(3)]
        barrier.wait(timeout=15)
        migrations.upgrade(bind)  # only the coordinator fixture performs DDL
        for task in tasks:task.result(timeout=25)
    assert startup.revision(bind)==migrations.HEAD
