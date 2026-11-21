# Alembic template scaffolding adapted under MIT; Copyright 2009-2026 Michael Bayer.
# See third_party/SOURCE_REVIEW.md (A001); project-specific migration policy is original.
"""${message}"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade():
    ${upgrades if upgrades else "pass"}


def downgrade():
    raise RuntimeError('默认禁止破坏性降级；请先制定并审核数据保留与应用回滚方案')
