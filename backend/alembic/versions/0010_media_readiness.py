"""Immutable upload derivatives and an order index; explicit initialization only."""
from alembic import op
import sqlalchemy as sa
revision='0010_media_readiness'
down_revision='0009_archive_discovery'
branch_labels=None
depends_on=None

def upgrade():
    for name in ['preview_width','preview_height']:
        op.add_column('media_assets',sa.Column(name,sa.Integer(),nullable=True,server_default=sa.text('NULL')))
    op.add_column('media_assets',sa.Column('thumbnail_sha256',sa.String(64),nullable=True,server_default=sa.text('NULL')))
    op.create_index('ix_records_active_order','content_records',[sa.text('display_date DESC'),'id'],postgresql_where=sa.text('deleted_at IS NULL'),sqlite_where=sa.text('deleted_at IS NULL'))

def downgrade():
    raise RuntimeError('拒绝删除：媒体派生信息与当前应用版本绑定，请使用兼容0010镜像或前向修复；不可删除数据卷回退')
