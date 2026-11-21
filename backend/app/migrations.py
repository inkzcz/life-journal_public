"""Explicit upgrades plus strictly empty-database bootstrap. Imports never write."""
from pathlib import Path
from contextlib import contextmanager, nullcontext
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text, UniqueConstraint
from .legacy_schema import metadata as legacy_metadata

HEAD = '0021_anniversary_calendar'
ALBUM_BASELINE = '0020_photo_albums'
CALENDAR_TABLES = {'anniversaries','anniversary_reminders'}
EXPERIENCE_BASELINE = '0019_unified_experiences'
ALBUM_TABLES = {'photo_albums','photo_album_photos'}
EXCHANGE_BASELINE = '0018_content_exchange'
EXPERIENCE_TABLES = {'article_options','experiences','experience_media','activity_experiences'}
ORGANIZATION_BASELINE = '0017_v5_organization'
EXCHANGE_TABLES={'exchange_jobs','exchange_file_operations','ai_invocations'}
MARKDOWN_BASELINE = '0016_markdown_travel'
V5_TABLES={'record_media_folders','media_archive_rules','media_archive_plans','food_content_types','food_occurrences'}
TRAVEL_BASELINE = '0015_travel_editing'
PLACE_BASELINE = '0014_place_identity'
MEDIA_RECOVERY_BASELINE = '0013_media_recovery'
PLACE_TABLES = {'place_aliases','revision_place_refs'}
MARKDOWN_TABLES={'record_marked_places'}
FOLDER_BASELINE = '0012_media_folders'
MEDIA_RECOVERY_TABLES = {'media_purge_operations','resource_reference_audits'}
WRITING_BASELINE = '0011_immersive_writing'
FOLDER_TABLES = {'media_folders'}
MEDIA_BASELINE = '0010_media_readiness'
WRITING_TABLES = {'record_body_media','revision_media_refs','media_upload_operations'}
DISCOVERY_BASELINE = '0009_archive_discovery'
RECOVERY_BASELINE = '0008_recovery'
DISCOVERY_TABLES = {'tags','record_tags','journal_tag_identities'}
LIFE_BASELINE = '0007_life_archive'
RECOVERY_TABLES = {'maintenance_jobs','backup_artifacts'}
TEMPLATE_BASELINE = '0006_content_templates'
LIFE_TABLES = {'trip_plans','trip_activities','trip_activity_media','photo_annotations'}
BLOG_BASELINE = '0005_blog_presentation'
TEMPLATE_TABLES = {'content_templates','template_versions','record_templates'}
ARCHIVE_BASELINE = '0004_archive_resources'
BLOG_TABLES = {'sections','section_content_types','navigation_items','site_configs'}
CONTENT_BASELINE = '0003_dynamic_content'
ARCHIVE_TABLES = {'media_assets','record_media','record_links','places','record_places'}
ADMIN_BASELINE = '0002_admin_users'
DYNAMIC_TABLES = {'content_types','content_type_versions','field_definitions','version_fields','content_records','record_revisions'}
BASELINE = '0001_legacy'
PHASE1 = {'users', 'sessions', 'journals', 'media'}
# Phase 1 has four tables; Phase 2 adds journal_metadata and journal_tags (six total).
# Keep this derived baseline explicit and immutable.
PHASE2 = set(legacy_metadata.tables)


def config(connection=None):
    cfg = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    if connection is not None:
        cfg.attributes['connection'] = connection
    return cfg


def validate_legacy(connection, names):
    inspector = inspect(connection)
    for name in sorted(names):
        table = legacy_metadata.tables[name]
        actual = {col['name']: col for col in inspector.get_columns(name)}
        if set(actual) != set(table.columns.keys()):
            raise RuntimeError(f'旧数据库结构不匹配：{name} 字段，请先核对备份，禁止直接 stamp')
        for col in table.columns:
            found = actual[col.name]
            expected_type = str(col.type.compile(dialect=connection.dialect)).upper()
            actual_type = str(found['type'].compile(dialect=connection.dialect)).upper()
            serial_default = (connection.dialect.name == 'postgresql' and col.primary_key
                              and expected_type == 'INTEGER' and found.get('autoincrement')
                              and str(found.get('default', '')).startswith('nextval('))
            if (actual_type != expected_type or found['nullable'] != col.nullable
                    or (found.get('default') is not None and not serial_default)):
                raise RuntimeError(f'旧数据库结构不匹配：{name}.{col.name} 类型/空值/默认值')
        pk = inspector.get_pk_constraint(name)['constrained_columns']
        if pk != [col.name for col in table.primary_key.columns]:
            raise RuntimeError(f'旧数据库结构不匹配：{name} 主键')
        uniques = {tuple(c['column_names']) for c in inspector.get_unique_constraints(name)}
        expected_uniques = {tuple(c.name for c in constraint.columns) for constraint in table.constraints if isinstance(constraint, UniqueConstraint)}
        if uniques != expected_uniques:
            raise RuntimeError(f'旧数据库结构不匹配：{name} 唯一约束')
        indexes = {(tuple(i['column_names']), bool(i['unique'])) for i in inspector.get_indexes(name)}
        expected_indexes = {(tuple(c.name for c in i.columns), bool(i.unique)) for i in table.indexes}
        if not expected_indexes <= indexes:
            raise RuntimeError(f'旧数据库结构不匹配：{name} 索引')
        fks = {(tuple(f['constrained_columns']), f['referred_table'], tuple(f['referred_columns']), f.get('options', {}).get('ondelete')) for f in inspector.get_foreign_keys(name)}
        expected_fks = {(tuple(c.name for c in fk.columns), next(iter(fk.elements)).column.table.name,
                         tuple(e.column.name for e in fk.elements), fk.ondelete) for fk in table.foreign_key_constraints}
        if fks != expected_fks or inspector.get_check_constraints(name):
            raise RuntimeError(f'旧数据库结构不匹配：{name} 外键/检查约束')


def ensure_legacy_schema(connection):
    names = set(inspect(connection).get_table_names()) - {'alembic_version'}
    if names not in (set(), PHASE1, PHASE2):
        raise RuntimeError('不是空数据库或完整 Phase 1/2 数据库；停止升级，禁止直接 stamp')
    validate_legacy(connection, names)
    missing = [legacy_metadata.tables[name] for name in sorted(PHASE2 - names)]
    legacy_metadata.create_all(connection, tables=missing)


def preflight(bind):
    """Read-only inspection: no stamping, DDL, users or files are modified."""
    with bind.connect() as connection:
        names = set(inspect(connection).get_table_names())
        if 'alembic_version' in names:
            revisions = set(connection.execute(text('SELECT version_num FROM alembic_version')).scalars())
            if revisions:
                if revisions not in ({BASELINE}, {ADMIN_BASELINE}, {CONTENT_BASELINE}, {ARCHIVE_BASELINE}, {BLOG_BASELINE}, {TEMPLATE_BASELINE}, {LIFE_BASELINE}, {RECOVERY_BASELINE}, {DISCOVERY_BASELINE}, {MEDIA_BASELINE}, {WRITING_BASELINE}, {FOLDER_BASELINE}, {MEDIA_RECOVERY_BASELINE}, {PLACE_BASELINE}, {TRAVEL_BASELINE}, {MARKDOWN_BASELINE}, {ORGANIZATION_BASELINE}, {EXCHANGE_BASELINE}, {EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):
                    raise RuntimeError('数据库版本不兼容，停止升级')
                expected = PHASE2 | {'alembic_version'}
                if revisions in ({ADMIN_BASELINE}, {CONTENT_BASELINE}, {ARCHIVE_BASELINE}, {BLOG_BASELINE}, {TEMPLATE_BASELINE}, {LIFE_BASELINE}, {RECOVERY_BASELINE}, {DISCOVERY_BASELINE}, {MEDIA_BASELINE}, {WRITING_BASELINE}, {FOLDER_BASELINE}, {MEDIA_RECOVERY_BASELINE}, {PLACE_BASELINE}, {TRAVEL_BASELINE}, {MARKDOWN_BASELINE}, {ORGANIZATION_BASELINE}, {EXCHANGE_BASELINE}, {EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):
                    expected.add('admin_users')
                if revisions in ({CONTENT_BASELINE}, {ARCHIVE_BASELINE}, {BLOG_BASELINE}, {TEMPLATE_BASELINE}, {LIFE_BASELINE}, {RECOVERY_BASELINE}, {DISCOVERY_BASELINE}, {MEDIA_BASELINE}, {WRITING_BASELINE}, {FOLDER_BASELINE}, {MEDIA_RECOVERY_BASELINE}, {PLACE_BASELINE}, {TRAVEL_BASELINE}, {MARKDOWN_BASELINE}, {ORGANIZATION_BASELINE}, {EXCHANGE_BASELINE}, {EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):
                    expected |= DYNAMIC_TABLES
                if revisions in ({ARCHIVE_BASELINE}, {BLOG_BASELINE}, {TEMPLATE_BASELINE}, {LIFE_BASELINE}, {RECOVERY_BASELINE}, {DISCOVERY_BASELINE}, {MEDIA_BASELINE}, {WRITING_BASELINE}, {FOLDER_BASELINE}, {MEDIA_RECOVERY_BASELINE}, {PLACE_BASELINE}, {TRAVEL_BASELINE}, {MARKDOWN_BASELINE}, {ORGANIZATION_BASELINE}, {EXCHANGE_BASELINE}, {EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):
                    expected |= ARCHIVE_TABLES
                if revisions in ({BLOG_BASELINE}, {TEMPLATE_BASELINE}, {LIFE_BASELINE}, {RECOVERY_BASELINE}, {DISCOVERY_BASELINE}, {MEDIA_BASELINE}, {WRITING_BASELINE}, {FOLDER_BASELINE}, {MEDIA_RECOVERY_BASELINE}, {PLACE_BASELINE}, {TRAVEL_BASELINE}, {MARKDOWN_BASELINE}, {ORGANIZATION_BASELINE}, {EXCHANGE_BASELINE}, {EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):
                    expected |= BLOG_TABLES
                if revisions in ({TEMPLATE_BASELINE}, {LIFE_BASELINE}, {RECOVERY_BASELINE}, {DISCOVERY_BASELINE}, {MEDIA_BASELINE}, {WRITING_BASELINE}, {FOLDER_BASELINE}, {MEDIA_RECOVERY_BASELINE}, {PLACE_BASELINE}, {TRAVEL_BASELINE}, {MARKDOWN_BASELINE}, {ORGANIZATION_BASELINE}, {EXCHANGE_BASELINE}, {EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):
                    expected |= TEMPLATE_TABLES
                if revisions in ({LIFE_BASELINE}, {RECOVERY_BASELINE}, {DISCOVERY_BASELINE}, {MEDIA_BASELINE}, {WRITING_BASELINE}, {FOLDER_BASELINE}, {MEDIA_RECOVERY_BASELINE}, {PLACE_BASELINE}, {TRAVEL_BASELINE}, {MARKDOWN_BASELINE}, {ORGANIZATION_BASELINE}, {EXCHANGE_BASELINE}, {EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):
                    expected |= LIFE_TABLES
                if revisions in ({RECOVERY_BASELINE}, {DISCOVERY_BASELINE}, {MEDIA_BASELINE}, {WRITING_BASELINE}, {FOLDER_BASELINE}, {MEDIA_RECOVERY_BASELINE}, {PLACE_BASELINE}, {TRAVEL_BASELINE}, {MARKDOWN_BASELINE}, {ORGANIZATION_BASELINE}, {EXCHANGE_BASELINE}, {EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):
                    expected |= RECOVERY_TABLES
                if revisions in ({DISCOVERY_BASELINE}, {MEDIA_BASELINE}, {WRITING_BASELINE}, {FOLDER_BASELINE}, {MEDIA_RECOVERY_BASELINE}, {PLACE_BASELINE}, {TRAVEL_BASELINE}, {MARKDOWN_BASELINE}, {ORGANIZATION_BASELINE}, {EXCHANGE_BASELINE}, {EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):
                    expected |= DISCOVERY_TABLES
                if revisions in ({WRITING_BASELINE},{FOLDER_BASELINE},{MEDIA_RECOVERY_BASELINE}, {PLACE_BASELINE}, {TRAVEL_BASELINE}, {MARKDOWN_BASELINE}, {ORGANIZATION_BASELINE}, {EXCHANGE_BASELINE}, {EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):
                    expected |= WRITING_TABLES
                if revisions in ({FOLDER_BASELINE},{MEDIA_RECOVERY_BASELINE}, {PLACE_BASELINE}, {TRAVEL_BASELINE}, {MARKDOWN_BASELINE}, {ORGANIZATION_BASELINE}, {EXCHANGE_BASELINE}, {EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):
                    expected |= FOLDER_TABLES
                if revisions in ({MEDIA_RECOVERY_BASELINE}, {PLACE_BASELINE}, {TRAVEL_BASELINE}, {MARKDOWN_BASELINE}, {ORGANIZATION_BASELINE}, {EXCHANGE_BASELINE}, {EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):
                    expected |= MEDIA_RECOVERY_TABLES
                if revisions in ({PLACE_BASELINE}, {TRAVEL_BASELINE}, {MARKDOWN_BASELINE}, {ORGANIZATION_BASELINE}, {EXCHANGE_BASELINE}, {EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):expected |= PLACE_TABLES
                if revisions in ({MARKDOWN_BASELINE}, {ORGANIZATION_BASELINE}, {EXCHANGE_BASELINE}, {EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):expected |= MARKDOWN_TABLES
                if revisions in ({ORGANIZATION_BASELINE},{EXCHANGE_BASELINE}, {EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):expected |= V5_TABLES
                if revisions in ({EXCHANGE_BASELINE}, {EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):expected |= EXCHANGE_TABLES
                if revisions in ({EXPERIENCE_BASELINE}, {ALBUM_BASELINE}, {HEAD}):expected |= EXPERIENCE_TABLES
                if revisions in ({ALBUM_BASELINE}, {HEAD}):expected |= ALBUM_TABLES
                if revisions == {HEAD}:expected |= CALENDAR_TABLES
                if names != expected:
                    raise RuntimeError('已标记版本与实际表不匹配，停止升级')
                validate_legacy(connection, PHASE2)
                return 'current' if revisions == {HEAD} else ('phase4a' if revisions == {MEDIA_BASELINE} else 'phase3l' if revisions == {DISCOVERY_BASELINE} else 'phase3h' if revisions == {RECOVERY_BASELINE} else 'phase3f' if revisions == {LIFE_BASELINE} else 'phase3e' if revisions == {TEMPLATE_BASELINE} else 'phase3d' if revisions == {BLOG_BASELINE} else 'phase3c' if revisions == {ARCHIVE_BASELINE} else ('phase3b' if revisions == {CONTENT_BASELINE} else ('phase3a' if revisions == {ADMIN_BASELINE} else 'baseline')))
            names.remove('alembic_version')
        if names not in (set(), PHASE1, PHASE2):
            raise RuntimeError('不是空数据库或完整 Phase 1/2 数据库；停止升级，禁止直接 stamp')
        validate_legacy(connection, names)
        return 'empty' if not names else ('phase1' if names == PHASE1 else 'phase2')


MIGRATION_LOCK = 721934011

@contextmanager
def migration_lock(bind):
    """Same database-scoped lock as empty bootstrap; crashes release it in PG."""
    if bind.dialect.name != 'postgresql':
        yield
        return
    with bind.connect().execution_options(isolation_level='AUTOCOMMIT') as con:
        con.execute(text("SET lock_timeout='30s'"))
        con.scalar(text(f'SELECT pg_advisory_lock({MIGRATION_LOCK})'))
        try:
            yield
        finally:
            con.scalar(text(f'SELECT pg_advisory_unlock({MIGRATION_LOCK})'))


def upgrade(bind):
    # All supported manual upgrades obey the same order as automatic startup.
    from .services.write_barrier import frozen
    with migration_lock(bind), frozen(bind) if bind.dialect.name == 'postgresql' else nullcontext():
        preflight(bind)
        with bind.begin() as connection:
            command.upgrade(config(connection), 'head')
            _require_current_schema(connection)


def require_current_schema(bind):
    with bind.connect() as connection:
        _require_current_schema(connection)

def _require_current_schema(connection):
    if 'alembic_version' not in inspect(connection).get_table_names():
        raise RuntimeError('数据库未初始化：请先运行 python -m app.migrate upgrade')
    revisions = set(connection.execute(text('SELECT version_num FROM alembic_version')).scalars())
    if revisions != {HEAD}:
        raise RuntimeError('数据库版本不兼容：请运行 python -m app.migrate check / upgrade')
    names = set(inspect(connection).get_table_names())
    validate_exchange_schema(connection)
    validate_experience_schema(connection)
    from .album_models import Album, AlbumPhoto
    validate_tables(connection,(Album.__table__,AlbumPhoto.__table__))
    from .calendar.models import Anniversary, Reminder
    validate_tables(connection,(Anniversary.__table__,Reminder.__table__))
    if not V5_TABLES <= names:raise RuntimeError('动态内容表缺失（v5组织），禁止绕过升级')
    required_v5={'record_media_folders':{'record_id','folder_id'},'media_archive_rules':{'id','name','enabled','date_source','fallback','granularity','by_type','parent_id','revision','created_by'},'media_archive_plans':{'id','rule_id','rule_revision','actor_id','items','completed','created_at'},'food_content_types':{'type_id','template_id'},'food_occurrences':{'id','record_id','source_key','source_kind','name','description','day','place_id','city','city_source','city_override','category','active','revision'}}
    for table,columns in required_v5.items():
        if columns!={c['name'] for c in inspect(connection).get_columns(table)}:raise RuntimeError('动态内容表缺失或v5字段不匹配，停止启动')
    if not DYNAMIC_TABLES | ARCHIVE_TABLES | BLOG_TABLES | TEMPLATE_TABLES | LIFE_TABLES | RECOVERY_TABLES | DISCOVERY_TABLES | WRITING_TABLES | FOLDER_TABLES | MEDIA_RECOVERY_TABLES | PLACE_TABLES | MARKDOWN_TABLES <= names:
        raise RuntimeError('动态内容表缺失：请核对数据库结构，禁止绕过版本检查')
    for table,columns in {'content_records':{'summary'},'media_assets':{'captured_on'},'trip_activities':{'markdown_owned'},'record_places':{'markdown_owned'}}.items():
        if not columns <= {c['name'] for c in inspect(connection).get_columns(table)}:raise RuntimeError('数据库新增字段缺失：禁止绕过迁移版本检查')
    if 'admin_users' not in names:
        raise RuntimeError('管理员授权表缺失：请恢复数据库结构，禁止绕过版本检查')


def initialize_empty_database(bind):
    """Only an entirely empty PostgreSQL database may be initialized automatically.
    Lock is database scoped and held on the SAME connection as transactional DDL.
    Any foreign schema/table/view/sequence or failed partial install fails closed.
    """
    if bind.dialect.name!='postgresql':
        require_current_schema(bind)
        return
    with bind.begin() as con:
        con.execute(text("SET LOCAL lock_timeout='30s'"))
        con.execute(text('SELECT pg_advisory_xact_lock(721934011)'))
        names=set(inspect(con).get_table_names())
        if names:
            _require_current_schema(con)
            return
        objects=con.scalar(text("""SELECT count(*) FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname NOT IN ('pg_catalog','information_schema')
            AND n.nspname NOT LIKE 'pg_toast%' AND n.nspname NOT LIKE 'pg_temp%'
            AND c.relkind IN ('r','p','v','m','S','f')"""))
        schemas=con.scalar(text("SELECT count(*) FROM pg_namespace WHERE nspname NOT IN ('public','pg_catalog','information_schema') AND nspname NOT LIKE 'pg_%'"))
        extras=con.scalar(text("SELECT (SELECT count(*) FROM pg_extension WHERE extname!='plpgsql') + (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_%') + (SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_%' AND t.typtype IN ('e','d','c'))"))
        if objects or schemas or extras:
            raise RuntimeError('数据库包含未知对象，停止自动初始化；请管理员核对后显式升级')
        command.upgrade(config(con),'head')
        _require_current_schema(con)


def validate_exchange_schema(connection):
    from .exchange.models import ExchangeJob,ExchangeFileOperation,AIInvocation
    validate_tables(connection, (ExchangeJob.__table__, ExchangeFileOperation.__table__, AIInvocation.__table__))

def validate_experience_schema(connection):
    from .experience_models import ArticleOptions, Experience, ExperienceMedia, ActivityExperience
    validate_tables(connection, (ArticleOptions.__table__, Experience.__table__, ExperienceMedia.__table__,ActivityExperience.__table__))

def validate_tables(connection, tables):
    """Fail closed on missing/forged new structures, not just a version stamp."""
    from .exchange.models import ExchangeJob,ExchangeFileOperation,AIInvocation
    inspector=inspect(connection)
    for table in tables:
        if table.name not in inspector.get_table_names():raise RuntimeError('内容交换表缺失，停止启动')
        actual={c['name']:c for c in inspector.get_columns(table.name)}
        if set(actual)!=set(table.columns.keys()):raise RuntimeError('内容交换字段不匹配，停止启动')
        for c in table.columns:
            a=actual[c.name]
            if str(a['type'].compile(dialect=connection.dialect)).upper()!=str(c.type.compile(dialect=connection.dialect)).upper() or a['nullable']!=c.nullable or a.get('default') is not None:raise RuntimeError('内容交换字段类型或默认值不匹配，停止启动')
        if inspector.get_pk_constraint(table.name)['constrained_columns']!=[c.name for c in table.primary_key.columns]:raise RuntimeError('内容交换主键不匹配')
        expected={tuple(c.name for c in u.columns) for u in table.constraints if isinstance(u,UniqueConstraint)}
        if expected!={tuple(u['column_names']) for u in inspector.get_unique_constraints(table.name)}:raise RuntimeError('内容交换唯一约束不匹配')
        expected_fk={(tuple(c.name for c in fk.columns),next(iter(fk.elements)).column.table.name,tuple(e.column.name for e in fk.elements),fk.ondelete) for fk in table.foreign_key_constraints}
        actual_fk={(tuple(f['constrained_columns']),f['referred_table'],tuple(f['referred_columns']),f.get('options',{}).get('ondelete')) for f in inspector.get_foreign_keys(table.name)}
        if expected_fk!=actual_fk:raise RuntimeError('内容交换外键不匹配')
        indexes={(tuple(i['column_names']),bool(i['unique'])) for i in inspector.get_indexes(table.name)}
        if not {(tuple(c.name for c in i.columns),bool(i.unique)) for i in table.indexes}<=indexes:raise RuntimeError('内容交换索引不匹配')
        from sqlalchemy import CheckConstraint
        if {c.name for c in table.constraints if isinstance(c,CheckConstraint)}!={c['name'] for c in inspector.get_check_constraints(table.name)}:raise RuntimeError('内容交换检查约束不匹配')
