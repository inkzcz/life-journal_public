"""Additive 0017 -> 0018 verification with qualified, exact-hash authorization."""
import json,uuid
from pathlib import Path
import pytest
from sqlalchemy import create_engine,inspect,select,text,MetaData
from alembic import command
from test_api import reset_limiter,engine
from app import migrations,auto_migrate


def fresh(tmp_path):
    if engine.dialect.name=='postgresql':
        name='lj_exchange_migration_'+uuid.uuid4().hex[:12]
        with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as c:c.execute(text('CREATE DATABASE '+name))
        return create_engine(engine.url.set(database=name),hide_parameters=True)
    return create_engine('sqlite:///'+str(tmp_path/'isolated-migration.db'))


def source(bind):
    with bind.begin() as c:command.upgrade(migrations.config(c),'0017_v5_organization')
    from sqlalchemy.orm import Session
    from app.models import User,AdminUser
    from app.content_models import ContentType
    from app.content_schemas import TypeCreate,RecordCreate
    from app.services.content import save_version,create_record_in_transaction
    with Session(bind) as db:
        user=User(username='synthetic-old-owner',password_hash='synthetic-not-login-hash');db.add(user);db.flush();db.add(AdminUser(user_id=user.id))
        t=ContentType(id=str(uuid.uuid4()),slug='synthetic-old-type',name='旧自定义类型',active=True,revision=1)
        db.add(t);db.flush();save_version(db,t,TypeCreate(slug=t.slug,name=t.name,fields=[]),user.id)
        from app.content_models import ContentRecord
        from datetime import date
        db.add(ContentRecord(id=str(uuid.uuid4()),type_id=t.id,schema_version=1,title='原文章完整保留',body='原始Markdown\n\n@l 合成城市',display_date=date(2026,10,1),status='draft',values={}));db.commit()


def fingerprint(bind):
    metadata=MetaData();metadata.reflect(bind=bind);out={}
    with bind.connect() as c:
        for t in metadata.sorted_tables:
            if t.name=='alembic_version':continue
            rows=c.execute(select(t).order_by(*t.primary_key.columns)).all()
            out[t.name]=json.dumps([list(x) for x in rows],default=str,sort_keys=True,ensure_ascii=False)
    return out


def test_old_schema_upgrade_repeat_and_all_original_rows_unchanged(tmp_path):
    bind=fresh(tmp_path)
    try:
        source(bind);before=fingerprint(bind)
        migrations.upgrade(bind);migrations.upgrade(bind)
        after=fingerprint(bind)
        assert all(after[k]==v for k,v in before.items())
        assert set(after)-set(before)==migrations.EXCHANGE_TABLES|migrations.EXPERIENCE_TABLES|migrations.ALBUM_TABLES|migrations.CALENDAR_TABLES
        assert all(after[name]=='[]' for name in migrations.EXCHANGE_TABLES)
        with bind.connect() as c:
            assert c.scalar(text('SELECT version_num FROM alembic_version'))==migrations.HEAD
            migrations.validate_exchange_schema(c)
    finally:bind.dispose()  # Synthetic DB retained; never DROP a database/volume.


def test_new_automatic_edge_is_exactly_hash_pinned_after_real_restore_qualification(monkeypatch):
    auto_migrate.approved('0017_v5_organization','0018_content_exchange')
    auto_migrate.approved('0016_markdown_travel','0018_content_exchange')
    monkeypatch.setattr(auto_migrate,'APPROVED',{('0017_v5_organization','0018_content_exchange'):{'0018_content_exchange.py':'0'*64}})
    with pytest.raises(auto_migrate.GateError,match='校验和'):
        auto_migrate.approved('0017_v5_organization','0018_content_exchange')


def test_pg_transaction_failure_rolls_back_entire_new_migration(tmp_path):
    if engine.dialect.name!='postgresql':pytest.skip('Requires PostgreSQL transactional DDL, not simulated SQLite success')
    bind=fresh(tmp_path)
    try:
        source(bind);before=fingerprint(bind)
        with pytest.raises(RuntimeError,match='synthetic transaction failure'):
            with bind.begin() as c:
                command.upgrade(migrations.config(c),'head')
                raise RuntimeError('synthetic transaction failure')
        assert fingerprint(bind)==before
        with bind.connect() as c:assert c.scalar(text('SELECT version_num FROM alembic_version'))=='0017_v5_organization'
        assert not migrations.EXCHANGE_TABLES.intersection(inspect(bind).get_table_names())
    finally:bind.dispose()
