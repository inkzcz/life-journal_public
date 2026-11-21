"""Additive Markdown identities and capture dates; never rewrites existing content."""
from alembic import op
import sqlalchemy as sa
revision='0016_markdown_travel'
down_revision='0015_travel_editing'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('content_records',sa.Column('summary',sa.String(500),nullable=False,server_default=''))
    op.add_column('media_assets',sa.Column('captured_on',sa.Date(),nullable=True))
    op.add_column('record_places',sa.Column('markdown_owned',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('trip_activities',sa.Column('markdown_owned',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.create_table('record_marked_places',
        sa.Column('record_id',sa.Uuid(as_uuid=False),sa.ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('source_key',sa.String(64),primary_key=True),
        sa.Column('place_id',sa.Uuid(as_uuid=False),sa.ForeignKey('places.id',ondelete='RESTRICT'),nullable=False,index=True))

def downgrade():
    raise RuntimeError('拒绝删除摘要、拍摄日期和地点绑定；请前向修复或使用备份在独立目标恢复')
