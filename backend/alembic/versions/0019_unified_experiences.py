"""Add stable source cards and reversible article options; no historical rewrite."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = '0019_unified_experiences'
down_revision = '0018_content_exchange'
branch_labels = depends_on = None

def upgrade():
    op.create_table('article_options',
        sa.Column('record_id', sa.Uuid(as_uuid=False), sa.ForeignKey('content_records.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('end_date', sa.Date(), nullable=True), sa.Column('travel_enabled', sa.Boolean(), nullable=False))
    op.create_table('experiences',
        sa.Column('record_id', sa.Uuid(as_uuid=False), sa.ForeignKey('content_records.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column('kind', sa.String(1), nullable=False), sa.Column('name', sa.String(200), nullable=False),
        sa.Column('fields', sa.JSON().with_variant(JSONB(), 'postgresql'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False), sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False), sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('l','f','m','s','g','t')", name='ck_experience_kind'))
    op.create_index('ix_experiences_kind', 'experiences', ['kind'])
    op.create_table('experience_media',
        sa.Column('record_id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column('entry_id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column('media_id', sa.Uuid(as_uuid=False), sa.ForeignKey('media_assets.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('position', sa.Integer(), nullable=False), sa.Column('active', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['record_id','entry_id'], ['experiences.record_id','experiences.id'], ondelete='RESTRICT'))
    op.create_index('ix_experience_media_media_id','experience_media',['media_id'])

    op.create_table('activity_experiences',sa.Column('activity_id',sa.Uuid(as_uuid=False),sa.ForeignKey('trip_activities.id',ondelete='RESTRICT'),primary_key=True),sa.Column('record_id',sa.Uuid(as_uuid=False),nullable=False),sa.Column('entry_id',sa.Uuid(as_uuid=False),nullable=False),sa.ForeignKeyConstraint(['record_id','entry_id'],['experiences.record_id','experiences.id'],ondelete='RESTRICT'))

def downgrade():
    raise RuntimeError('新正文卡片不可由旧版本解释；请在隔离空目标恢复升级前备份，不删除经历或原文')
