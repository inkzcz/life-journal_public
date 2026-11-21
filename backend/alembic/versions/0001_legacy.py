"""Create an empty database or validate/adopt the frozen Phase 1/2 schema."""
from alembic import op
from app.migrations import ensure_legacy_schema

revision = '0001_legacy'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    ensure_legacy_schema(op.get_bind())


def downgrade():
    raise RuntimeError('拒绝删除旧表。请回退应用并保留数据库，参阅 docs/phase3a-upgrade.md')
