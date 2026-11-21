"""Fail-closed, maintenance-only startup gate; never restores or downgrades source.
Upgrade bundles are deliberately separate from ordinary same-build backups.
Only explicitly reviewed, hash-pinned additive edges may run automatically.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
import tempfile
from pathlib import Path
from contextlib import nullcontext
from datetime import datetime, timezone
from alembic import command
from sqlalchemy import MetaData, Table, String, create_engine, inspect, select, text
from types import SimpleNamespace
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from . import migrations
from . import backup
from .services.write_barrier import frozen

FORMAT = 'life-journal-upgrade-v1'
READY = Path('/tmp/life-journal-startup-ready.json')
# Adding a migration does NOT authorize it for automatic execution. Review its
# data semantics and update this exact edge/hash only after restore tests pass.
APPROVED = {
    # Actual PG17 dump, isolated restore, source-read guard and trial: docs/v5.1.9/migration-qualification.json.
    ('0016_markdown_travel', '0021_anniversary_calendar'): {
        '0017_v5_organization.py': 'd40cc75a8b53bc7da899112744a444ff2673ac843e3f0747799154b8036f3607',
        '0018_content_exchange.py': '87e76e901d6bb6f0d317fbcd9b09f272afa8aa915e32f3459a6a3b12d523bb2d',
        '0019_unified_experiences.py': '4e23664ef971c8b4c7c86f24fe83cdf8a9d5f7f6ff6ce68503786a0d04efcc4e',
        '0020_photo_albums.py': 'cb9fa319f8180aea7add67f41c14757d82ed7e5e75ffdf3563065227d3d8efae',
        '0021_anniversary_calendar.py': '16f0a49c97bdf5793c303450c21626dcaa5663d4303f04a30e8113b68b9b142b',
    },
    # Actual PG17 dump, isolated restore, source-read guard and trial: docs/v5.1.9/migration-qualification.json.
    ('0017_v5_organization', '0021_anniversary_calendar'): {
        '0018_content_exchange.py': '87e76e901d6bb6f0d317fbcd9b09f272afa8aa915e32f3459a6a3b12d523bb2d',
        '0019_unified_experiences.py': '4e23664ef971c8b4c7c86f24fe83cdf8a9d5f7f6ff6ce68503786a0d04efcc4e',
        '0020_photo_albums.py': 'cb9fa319f8180aea7add67f41c14757d82ed7e5e75ffdf3563065227d3d8efae',
        '0021_anniversary_calendar.py': '16f0a49c97bdf5793c303450c21626dcaa5663d4303f04a30e8113b68b9b142b',
    },
    # Actual PG17 dump, isolated restore, source-read guard and trial: docs/v5.1.9/migration-qualification.json.
    ('0018_content_exchange', '0021_anniversary_calendar'): {
        '0019_unified_experiences.py': '4e23664ef971c8b4c7c86f24fe83cdf8a9d5f7f6ff6ce68503786a0d04efcc4e',
        '0020_photo_albums.py': 'cb9fa319f8180aea7add67f41c14757d82ed7e5e75ffdf3563065227d3d8efae',
        '0021_anniversary_calendar.py': '16f0a49c97bdf5793c303450c21626dcaa5663d4303f04a30e8113b68b9b142b',
    },

    # 2026-11-05: actual PG17 dump + independent restore/trial and source-read
    # guard; see docs/v5.1.5/migration-qualification.json. No source rows changed.
    ('0017_v5_organization', '0018_content_exchange'): {
        '0018_content_exchange.py': '87e76e901d6bb6f0d317fbcd9b09f272afa8aa915e32f3459a6a3b12d523bb2d',
    },
    ('0016_markdown_travel', '0018_content_exchange'): {
        '0017_v5_organization.py': 'd40cc75a8b53bc7da899112744a444ff2673ac843e3f0747799154b8036f3607',
        '0018_content_exchange.py': '87e76e901d6bb6f0d317fbcd9b09f272afa8aa915e32f3459a6a3b12d523bb2d',
    },
    # PG17 actual restore/trial + source rollback: Actions 40342850990.
    ('0016_markdown_travel', '0017_v5_organization'): {
        '0017_v5_organization.py': 'd40cc75a8b53bc7da899112744a444ff2673ac843e3f0747799154b8036f3607',
    },
    ('0015_travel_editing', '0016_markdown_travel'): {
        '0016_markdown_travel.py': '3f833a6fd935a36b45b59ec22be608b302c633d81a0f52194d904c0caadaf3e4',
    },
}

class GateError(RuntimeError):
    """Only fixed, public diagnostic messages; no driver exception interpolation."""


def atomic_json(path, data):
    path = backup.no_symlinks(path)
    temp = path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
    with temp.open('x') as stream:
        os.chmod(temp, 0o600)
        json.dump(data, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def schema(bind):
    with bind.connect() as con:
        if not inspect(con).has_table('alembic_version'):
            raise GateError('未标记版本的旧库不允许自动采用；请先核对备份并人工升级')
        values = list(con.scalars(text('SELECT version_num FROM alembic_version')))
    if len(values) != 1:
        raise GateError('数据库版本标记不唯一，停止自动升级；请核对备份后人工排查')
    return values[0]


def approved(source, target):
    pinned = APPROVED.get((source, target))
    if not pinned:
        raise GateError('此升级路径未获自动迁移授权；不会修改数据库，请使用兼容版本或人工升级流程')
    root = Path(__file__).resolve().parents[1] / 'alembic' / 'versions'
    for filename, digest in pinned.items():
        if backup.sha(root / filename) != digest:
            raise GateError('迁移文件与已审核校验和不符，停止自动升级')
    # The approved file must be exactly the linear path Alembic will execute.
    from alembic.script import ScriptDirectory
    revisions = list(ScriptDirectory.from_config(migrations.config()).iterate_revisions(target, source))
    if {Path(r.path).name for r in revisions} != set(pinned):
        raise GateError('迁移图与已审核路径不一致，停止自动升级')


def metadata(bind):
    result = MetaData()
    result.reflect(bind=bind)
    return result


def fingerprint(bind, model=None, connection=None):
    model = model if model is not None else metadata(bind)
    result = {}
    with (nullcontext(connection) if connection is not None else bind.connect()) as con:
        if connection is None: con.execute(text('SET TRANSACTION READ ONLY'))
        con.execute(text("SET LOCAL statement_timeout='600s'"))
        con.execute(text("SET TIME ZONE 'UTC'"))
        for table in sorted(model.tables.values(), key=lambda t: t.name):
            if not table.primary_key.columns:
                raise GateError('数据库存在无稳定主键的表，停止自动升级')
            h = hashlib.sha256(); count = 0
            # Stable byte ordering across source/drill database locale settings.
            order = [c.collate('C') if isinstance(c.type, String) else c for c in table.primary_key.columns]
            for row in con.execute(select(table).order_by(*order).execution_options(stream_results=True)).yield_per(500):
                h.update(json.dumps(list(row),sort_keys=True,ensure_ascii=False,default=str,separators=(',',':')).encode())
                h.update(b'\n'); count += 1
            result[table.name] = {'rows': count, 'sha256': h.hexdigest()}
        sequences = {}
        for name in con.scalars(text("SELECT sequencename FROM pg_sequences WHERE schemaname=current_schema() ORDER BY sequencename")):
            quoted = con.dialect.identifier_preparer.quote(name)
            sequences[name] = list(con.execute(text(f'SELECT last_value,is_called FROM {quoted}')).one())
        result['__sequences__'] = sequences
    return result


def validate_media(bind, root):
    # Only currently approved 0015+ layouts are used here. Management-only new
    # columns stay deferred; no source rows/files are mutated by this validator.
    from .services.media_recovery import validate_backup_media
    asset_table = Table('media_assets', MetaData(), autoload_with=bind)
    with Session(bind) as db:
        assets = [SimpleNamespace(**{k: str(v) if isinstance(v, uuid.UUID) else v for k,v in row.items()})
                  for row in db.execute(select(asset_table)).mappings()]
        validate_backup_media(db, root, assets=assets)


def pg_run(bind, args):
    # Never put URLs/passwords on argv or send pg stderr to container logs.
    try:
        subprocess.run(args, env=backup.pg_env(bind), check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    except (subprocess.SubprocessError, OSError):
        tool = args[0] if args[0] in {'pg_dump','pg_restore'} else 'PostgreSQL'
        raise GateError(tool+' 工具失败或超时，未放行启动；请核对权限、空间及 PostgreSQL 17') from None


def verify_bundle(bundle):
    bundle = backup.no_symlinks(bundle)
    try:
        p = bundle/'manifest.json'
        if p.stat().st_size > 20*1024*1024:
            raise ValueError()
        m = json.loads(p.read_text())
        if m['format'] != FORMAT or m['complete'] is not True or m['postgresql_major'] != 17:
            raise ValueError()
        actual = backup.files(bundle); actual.pop('manifest.json', None)
        if actual != m['files'] or 'database.dump' not in actual or not (bundle/'media').is_dir():
            raise ValueError()
        if not isinstance(m['tables'], dict) or not isinstance(m['source_schema'], str):
            raise ValueError()
        return m
    except (OSError, ValueError, KeyError, TypeError):
        raise GateError('升级保护备份不完整或校验失败；原数据库未执行自动迁移') from None


def require_disjoint_media(source, destination):
    # Logical paths differ even if GUI bind mounts alias the same host directory.
    # Detect a backup root reachable below media BEFORE creating/copying bundles,
    # otherwise copytree could recursively include its own output and fill disk.
    source = backup.no_symlinks(source)
    destination = backup.no_symlinks(destination)
    if not destination.is_dir():
        raise backup.BackupError('SSD 备份目录不存在，请在 Docker GUI 创建并挂载专用目录')
    if not source.is_dir():
        raise GateError('媒体专用目录未挂载，停止自动升级')
    target = destination.stat()
    def walk_error(_):
        raise GateError('媒体目录无法完整检查，停止自动升级')
    for directory, _, _files in os.walk(source, topdown=True, followlinks=False, onerror=walk_error):
        found = Path(directory).stat()
        if (found.st_dev, found.st_ino) == (target.st_dev, target.st_ino):
            raise GateError('备份挂载与媒体实际重叠，禁止递归备份；请在 GUI 使用独立目录')


def create_bundle(bind, attempt, source):
    original = backup.no_symlinks(Path(os.environ['MEDIA_DIR']))
    if not original.is_dir():
        raise GateError('媒体目录不可用，无法创建完整升级保护备份')
    validate_media(bind, original)
    partial = attempt/'.bundle.partial'
    partial.mkdir(mode=0o700)
    pg_run(bind, ['pg_dump','--format=custom','--no-owner','--no-acl','--file',str(partial/'database.dump')])
    expected = backup.files(original)
    shutil.copytree(original, partial/'media')
    if backup.files(partial/'media') != expected:
        raise GateError('升级保护备份媒体复制校验失败')
    m = {'format': FORMAT, 'complete': True, 'postgresql_major': 17,
         'source_schema': source, 'target_schema': migrations.HEAD,
         'producer_build': backup.version(), 'created_at': datetime.now(timezone.utc).isoformat(),
         'tables': fingerprint(bind), 'files': backup.files(partial),
         'required_external_config': ['POSTGRES_USER','POSTGRES_PASSWORD','POSTGRES_DB','COOKIE_SECURE'],
         'consistency': 'exclusive writer barrier held continuously through backup, restore rehearsal and source commit'}
    atomic_json(partial/'manifest.json', m)
    for p in partial.rglob('*'):
        if p.is_file():
            with p.open('rb') as f: os.fsync(f.fileno())
    for d in sorted([partial, *[p for p in partial.rglob('*') if p.is_dir()]],key=lambda p:len(p.parts),reverse=True):
        fd = os.open(d, os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    os.rename(partial, attempt/'bundle')
    atomic_json(attempt/'bundle-published.json', {'complete': True})
    verify_bundle(attempt/'bundle')
    return m


def require_empty(bind):
    with bind.connect() as con:
        count = con.scalar(text("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
              AND c.relkind IN ('r','p','v','m','S','f')"""))
        schemas = con.scalar(text("SELECT count(*) FROM pg_namespace WHERE nspname NOT IN ('public','information_schema') AND nspname NOT LIKE 'pg_%'"))
        extras = con.scalar(text("SELECT (SELECT count(*) FROM pg_extension WHERE extname!='plpgsql') + (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_%') + (SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_%' AND t.typtype IN ('e','d','c'))"))
        if count or schemas or extras:
            raise GateError('恢复目标数据库非空，拒绝覆盖；绝不会恢复到原数据库')
        if backup.pg_major(con) != 17:
            raise GateError('自动迁移和升级保护恢复仅支持 PostgreSQL 17')


def restore_bundle(bind, bundle, media):
    """Manual/new scratch targets only. Caller MUST freeze target writers."""
    m = verify_bundle(bundle)
    media = backup.no_symlinks(media)
    require_empty(bind)
    if media.exists() and any(media.iterdir()):
        raise GateError('恢复目标媒体目录非空，拒绝覆盖')
    media.mkdir(mode=0o700, parents=True, exist_ok=True)
    shutil.copytree(bundle/'media', media, dirs_exist_ok=True)
    pg_run(bind, ['pg_restore','--exit-on-error','--single-transaction','--no-owner','--no-acl','--dbname',bind.url.database,str(bundle/'database.dump')])
    if schema(bind) != m['source_schema'] or fingerprint(bind) != m['tables']:
        raise GateError('实际恢复后的数据库与升级保护备份不一致')
    expected = {k.removeprefix('media/'): v for k,v in m['files'].items() if k.startswith('media/')}
    if backup.files(media) != expected:
        raise GateError('实际恢复后的媒体与升级保护备份不一致')
    validate_media(bind, media)
    return m


def restore_rehearsal(bind, attempt):
    # PG17 tools already exist in Maintenance. A short-lived, unprivileged PG
    # process listens ONLY on a private 0700 Unix socket, never TCP. No Docker
    # socket, fifth container, source CREATEDB privilege or source DB restore.
    pgdata = attempt/'drill-pgdata'
    socket = Path(tempfile.mkdtemp(prefix='ljpg-'))
    common = {'check': True, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL, 'timeout': 90}
    target = None
    started = False
    try:
        subprocess.run(['initdb','-D',str(pgdata),'--username=lj_upgrade_drill',
                        '--auth-local=trust','--auth-host=reject','--no-locale','--encoding=UTF8'], **common)
        options = "-c listen_addresses='' -c unix_socket_directories="+str(socket)+" -c shared_buffers=32MB -c max_connections=8 -c log_statement=none -c log_min_error_statement=panic -c log_min_messages=panic"
        subprocess.run(['pg_ctl','-D',str(pgdata),'-l','/dev/null','-w','-t','60','-o',options,'start'], **common)
        started = True
        target = create_engine(URL.create('postgresql+psycopg',username='lj_upgrade_drill',host=str(socket),database='postgres'),hide_parameters=True)
        m = restore_bundle(target, attempt/'bundle', attempt/'drill-media')
        old = metadata(target)
        before = fingerprint(target, old)
        with target.begin() as con:
            command.upgrade(migrations.config(con), 'head')
            migrations._require_current_schema(con)
            after = fingerprint(target, old, connection=con)
            before.pop('alembic_version'); after.pop('alembic_version')
            if before != after:
                raise GateError('试迁移改变了原有字段或序列，拒绝升级原数据库')
        report = {'backup_restore': 'passed', 'tables_and_sequences': 'passed',
                  'media_restore': 'passed', 'trial_migration': 'passed',
                  'original_values_preserved': True, 'source_access_for_restore': False,
                  'source_schema': m['source_schema'], 'target_schema': migrations.HEAD,
                  'manifest_sha256': backup.sha(attempt/'bundle'/'manifest.json'),
                  'isolation': 'private temporary PG17 process, Unix socket only; data retained'}
        atomic_json(attempt/'restore-report.json', report)
        return report
    finally:
        if target is not None: target.dispose()
        # Stop ONLY the instance created in this unique attempt directory. Never
        # remove the scratch data, source database, source media or any backup.
        if started:
            subprocess.run(['pg_ctl','-D',str(pgdata),'-m','fast','-w','-t','60','stop'], **common)
        if socket.exists() and not any(socket.iterdir()): socket.rmdir()


def run(bind, retry_token=''):
    if bind.dialect.name != 'postgresql':
        raise GateError('自动迁移只支持 PostgreSQL；其他环境请使用手动迁移')
    # Order: migration lock -> backup directory lock -> exclusive write barrier.
    # Manual migration now uses the same outer lock. All three release on crash.
    with migrations.migration_lock(bind):
        state = migrations.preflight(bind)
        from .api_startup import revision
        print(f'[Migration] Current revision: {revision(bind)}; Target revision: {migrations.HEAD}; Coordinator: Maintenance', flush=True)
        if state == 'current':
            migrations.require_current_schema(bind)
            return {'state': 'current', 'schema': migrations.HEAD}
        if state == 'empty':
            # Already hold the session lock: initialize on this separate connection
            # would self-block. Release outer lock before strictly-empty bootstrap.
            pass
        else:
            source = schema(bind)
            approved(source, migrations.HEAD)
            with bind.connect() as con:
                if backup.pg_major(con) != 17:
                    raise GateError('自动迁移只支持 PostgreSQL 17')
                unknown = con.scalar(text("""SELECT
                    (SELECT count(*) FROM pg_namespace WHERE nspname NOT IN ('public','information_schema') AND nspname NOT LIKE 'pg_%') +
                    (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('v','m','f','c')) +
                    (SELECT count(*) FROM pg_extension WHERE extname!='plpgsql') +
                    (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public') +
                    (SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public' AND t.typtype IN ('e','d'))
                    """))
                if unknown:
                    raise GateError('旧库包含不支持的自定义模式、视图、扩展或函数；停止自动迁移，请人工核对完整备份')
                identity = hashlib.sha256((str(bind.url.set(password=None))+':'+str(con.scalar(text('SELECT oid FROM pg_database WHERE datname=current_database()')))).encode()).hexdigest()
            require_disjoint_media(Path(os.environ['MEDIA_DIR']), backup.backup_root())
            backup.prepare_local_target()
            with backup.backup_lock(exclusive=True), frozen(bind):
                require_disjoint_media(Path(os.environ['MEDIA_DIR']), backup.backup_root())
                media_inventory = backup.files(backup.no_symlinks(Path(os.environ['MEDIA_DIR'])))
                with bind.connect() as con:
                    database_size = con.scalar(text('SELECT pg_database_size(current_database())'))
                reserve = 3*database_size + 2*sum(f['size'] for f in media_inventory.values()) + 256*1024*1024
                if shutil.disk_usage(backup.backup_root()).free < reserve:
                    raise GateError('升级保护空间不足：需要数据库恢复副本、两份媒体副本及安全余量；未修改原数据库')
                # No retry storm after crash/failure. A GUI environment edit is an
                # explicit rearm, not permission to skip backups or validation.
                root = backup.no_symlinks(backup.backup_root()/'.upgrades-v1'/identity)
                root.mkdir(mode=0o700, parents=True, exist_ok=True)
                checkpoint = root/'attempt.json'
                token_hash = hashlib.sha256(retry_token.encode()).hexdigest()
                used_tokens = []
                if checkpoint.exists():
                    backup.no_symlinks(checkpoint)
                    if checkpoint.stat().st_size > 65536:raise GateError('升级检查点不合法，停止自动重试')
                    old = json.loads(checkpoint.read_text())
                    if old.get('source') == source and old.get('target') == migrations.HEAD and old.get('state') != 'upgraded':
                        used_tokens = old.get('used_retry_token_hashes', [old.get('retry_token_hash')])
                        if not isinstance(used_tokens, list) or len(used_tokens)>64 or not all(isinstance(t,str) and len(t)==64 for t in used_tokens):
                            raise GateError('升级重试记录不合法，请人工核对；不会清空或跳过检查点')
                        if not retry_token or token_hash in used_tokens:
                            raise GateError('上次升级失败或中断，已停止自动重试；备份保留。排查后在 GUI 更换未使用的 AUTO_MIGRATION_RETRY_TOKEN 再重构')
                        if len(used_tokens)>=64:
                            raise GateError('升级重试次数已达安全上限，请人工排查，不再自动创建副本')
                used_tokens.append(token_hash)
                attempt = root/str(uuid.uuid4()); attempt.mkdir(mode=0o700)
                atomic_json(checkpoint, {'state': 'running', 'attempt': attempt.name,
                            'retry_token_hash': token_hash, 'used_retry_token_hashes': used_tokens, 'source': source, 'target': migrations.HEAD})
                try:
                    print('升级门禁：创建完整数据库和媒体保护包', flush=True)
                    phase = 'backup'
                    before = create_bundle(bind, attempt, source)
                    print('升级门禁：在独立 PostgreSQL 实际恢复并试迁移', flush=True)
                    phase = 'independent-restore-and-trial'
                    report = restore_rehearsal(bind, attempt)
                    # Source cannot have changed between backup and commit. Also
                    # catches unsupported direct SQL writers which ignore barriers.
                    old_model = metadata(bind)
                    if fingerprint(bind, old_model) != before['tables'] or schema(bind) != source:
                        raise GateError('原数据库在保护期间发生变化，停止自动迁移')
                    approved(source, migrations.HEAD)
                    print('升级门禁：恢复验证通过，开始原库事务迁移', flush=True)
                    phase = 'source-transaction'
                    with bind.begin() as con:
                        command.upgrade(migrations.config(con), 'head')
                        migrations._require_current_schema(con)
                        after = fingerprint(bind, old_model, connection=con)
                        original = dict(before['tables'])
                        after.pop('alembic_version'); original.pop('alembic_version')
                        if after != original:
                            raise GateError('升级改变原值，事务已停止；禁止启动或自动降级')
                    result = {'state': 'upgraded', 'source': source, 'schema': migrations.HEAD,
                              'attempt': attempt.name, 'restore_validation': report['backup_restore']}
                    atomic_json(attempt/'success.json', result)
                    atomic_json(checkpoint, {**result, 'retry_token_hash': token_hash})
                    return result
                except BaseException:
                    atomic_json(attempt/'failed.json', {'state': 'failed', 'phase': phase, 'source_not_automatically_restored': True})
                    raise
    # Empty initialization has its own transactional lock and unknown-object guard.
    migrations.initialize_empty_database(bind)
    return {'state': 'initialized', 'schema': migrations.HEAD}


def build_identity():
    # An unversioned local development build may initialize/no-op, as before.
    # create_bundle still calls backup.version(), which forbids unpinned upgrades.
    built = Path(__file__).resolve().parents[1]/'BUILD_VERSION'
    value = built.read_text().strip() if built.is_file() else os.getenv('LIFE_JOURNAL_VERSION','unversioned')
    return value if value == 'unversioned' else backup.version()


def startup(bind):
    try:
        READY.unlink(missing_ok=True)
        result = run(bind, os.getenv('AUTO_MIGRATION_RETRY_TOKEN',''))
        atomic_json(READY, {**result, 'build': build_identity()})
        print('数据库启动门禁通过：'+result['state']+'；未执行删除或降级', flush=True)
    except Exception as exc:
        if isinstance(exc, (GateError, backup.BackupError)):
            message = str(exc)
        else:
            message = '自动迁移安全停止：备份、恢复验证、权限、锁或迁移失败；请核对维护容器、磁盘空间和兼容版本'
        print(message, file=sys.stderr, flush=True)
        raise SystemExit(1) from None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['startup','restore'])
    p.add_argument('--bundle', type=Path)
    p.add_argument('--confirm-empty-target', action='store_true')
    args = p.parse_args()
    from .db import engine
    if args.action == 'startup':
        startup(engine); return
    try:
        if not args.confirm_empty_target or args.bundle is None:
            raise GateError('恢复需要明确指定升级保护备份及确认独立空目标')
        with migrations.migration_lock(engine), frozen(engine):
            restore_bundle(engine, backup.no_symlinks(args.bundle), Path(os.environ['MEDIA_DIR']))
        print('升级保护备份已恢复到独立空目标；请使用源模式兼容镜像启动并完成应用验收')
    except Exception:
        print('升级保护恢复停止；请核对完整备份、空目标、权限及 PostgreSQL 17，未自动删除或降级任何数据库',file=sys.stderr)
        raise SystemExit(1) from None

if __name__ == '__main__':
    main()
