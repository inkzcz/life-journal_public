"""API pre-HTTP coordination; DDL stays in the backup-capable Maintenance gate.

Never give the web-facing API a backup mount, pg tools or a bare upgrade path.
An old Compose must be replaced once: API -> Maintenance -> API is a deadlock.
"""
import os
import re
import time
from sqlalchemy import inspect, text
from . import migrations


class StartupError(RuntimeError):
    pass


def revision(bind):
    with bind.connect() as con:
        if bind.dialect.name == 'postgresql':
            con.execute(text("SET LOCAL statement_timeout='5s'"))
        if not inspect(con).has_table('alembic_version'):
            return 'unversioned-or-empty'
        rows = list(con.scalars(text('SELECT version_num FROM alembic_version')))
        if len(rows) != 1 or not isinstance(rows[0], str) or not re.fullmatch(r'[A-Za-z0-9_]{1,80}', rows[0]):
            raise StartupError('数据库版本标记非法或不唯一；保留数据，请核对兼容镜像和完整备份')
        return rows[0]


def prepare(bind, *, timeout=None, sleep=time.sleep, clock=time.monotonic):
    stage = 'revision'; current = 'unavailable'
    try:
        current = revision(bind)
        print(f'[Migration] Current revision: {current}; Target revision: {migrations.HEAD}', flush=True)
        if current in {'unversioned-or-empty', migrations.HEAD} or bind.dialect.name != 'postgresql':
            stage = 'initialize-or-verify'
            migrations.initialize_empty_database(bind)
        else:
            stage = 'preflight'
            migrations.preflight(bind)  # Read-only; success is NOT an upgrade.
            from .auto_migrate import approved
            approved(current, migrations.HEAD)  # Exact reviewed edge/hash only.
            print('[Migration] Preflight: passed; supported upgrade required', flush=True)
            if os.getenv('AUTO_MIGRATE_ON_STARTUP', 'true') != 'true':
                raise StartupError('自动迁移已关闭；请核对配置及完整备份，不会裸跑升级')
            if os.getenv('MIGRATION_COORDINATOR') != 'maintenance':
                raise StartupError('缺少Maintenance迁移协调配置；请同步导入配套Compose，维护容器只能依赖db，不能依赖API。不要覆盖入口为sleep或手动跳过门禁')
            stage = 'wait-maintenance-gate'
            seconds = int(os.getenv('MIGRATION_WAIT_SECONDS', '1800')) if timeout is None else timeout
            if not 0 <= seconds <= 3600:
                raise StartupError('迁移等待时间配置非法，允许0至3600秒')
            deadline = clock() + seconds
            print('[Migration] Waiting for Maintenance: full backup, independent PG17 restore/trial, transactional upgrade', flush=True)
            while True:
                observed = revision(bind)
                if observed == migrations.HEAD:
                    break
                if observed != current:
                    raise StartupError('等待期间版本出现非预期变化，停止启动；请保留备份并人工核对')
                if clock() >= deadline:
                    raise StartupError('Maintenance迁移未在期限内完成；API未启动。检查配套Compose依赖、同版本三镜像、维护容器脱敏日志、备份挂载/空间和失败检查点；故障排除后显式重新授权重试')
                sleep(min(1, max(0, deadline-clock())))
            stage = 'schema-verification'
            migrations.require_current_schema(bind)
        print('[Migration] Schema verification: passed', flush=True)
    except Exception as error:
        from .auto_migrate import GateError
        reason = str(error) if isinstance(error, (StartupError, GateError)) else '预检查、授权路径、结构或数据库连接失败；请查看维护门禁日志，禁止跳过版本校验'
        # Preserve diagnostic categories, not arbitrary driver text/SQL parameters.
        if not isinstance(error, (StartupError, GateError)):
            for marker in ['未知对象','数据库未初始化','数据库版本不兼容','动态内容表缺失','已标记版本与实际表不匹配']:
                if marker in str(error):
                    reason = marker+'；停止启动，保留数据并核对配套镜像、Compose和完整备份';break
        print(f'[Migration] Failed phase: {stage}; Current: {current}; Target: {migrations.HEAD}; {reason}; API not started', flush=True)
        raise StartupError(reason) from None
