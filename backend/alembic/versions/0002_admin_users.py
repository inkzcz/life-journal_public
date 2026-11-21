"""Add explicit Admin grants; never promote existing users automatically."""
from alembic import op
import sqlalchemy as sa

revision = '0002_admin_users'
down_revision = '0001_legacy'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('admin_users',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('user_id'))


def downgrade():
    raise RuntimeError('拒绝删除授权数据。应用回滚时保留 admin_users 和 Alembic 版本表')
