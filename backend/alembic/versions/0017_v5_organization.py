"""Add logical organization and derived food indexes, preserving every old row."""
from alembic import op
import sqlalchemy as sa
revision='0017_v5_organization'
down_revision='0016_markdown_travel'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('record_media_folders',
        sa.Column('record_id',sa.Uuid(as_uuid=False),sa.ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('folder_id',sa.Uuid(as_uuid=False),sa.ForeignKey('media_folders.id',ondelete='RESTRICT'),nullable=False,unique=True))
    op.create_table('media_archive_rules',
        sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),sa.Column('name',sa.String(100),nullable=False),
        sa.Column('enabled',sa.Boolean(),nullable=False),sa.Column('date_source',sa.String(20),nullable=False),
        sa.Column('fallback',sa.String(20),nullable=False),sa.Column('granularity',sa.String(10),nullable=False),
        sa.Column('by_type',sa.Boolean(),nullable=False),sa.Column('parent_id',sa.Uuid(as_uuid=False),sa.ForeignKey('media_folders.id',ondelete='RESTRICT')),
        sa.Column('revision',sa.Integer(),nullable=False),sa.Column('created_by',sa.Integer(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.CheckConstraint("date_source IN ('uploaded','captured')",name='ck_archive_source'),
        sa.CheckConstraint("fallback IN ('uploaded','unknown')",name='ck_archive_fallback'),
        sa.CheckConstraint("granularity IN ('year','month','day')",name='ck_archive_granularity'))
    op.create_table('media_archive_plans',
        sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),
        sa.Column('rule_id',sa.Uuid(as_uuid=False),sa.ForeignKey('media_archive_rules.id',ondelete='RESTRICT'),nullable=False,index=True),
        sa.Column('rule_revision',sa.Integer(),nullable=False),sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('items',sa.JSON().with_variant(sa.dialects.postgresql.JSONB(),'postgresql'),nullable=False),
        sa.Column('completed',sa.Boolean(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('food_content_types',sa.Column('type_id',sa.Uuid(as_uuid=False),sa.ForeignKey('content_types.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('template_id',sa.Uuid(as_uuid=False),sa.ForeignKey('content_templates.id',ondelete='RESTRICT'),nullable=False,unique=True))
    op.create_table('food_occurrences',sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),
        sa.Column('record_id',sa.Uuid(as_uuid=False),sa.ForeignKey('content_records.id',ondelete='RESTRICT'),nullable=False,index=True),
        sa.Column('source_key',sa.String(160),nullable=False),sa.Column('source_kind',sa.String(20),nullable=False),
        sa.Column('name',sa.String(200),nullable=False),sa.Column('description',sa.Text(),nullable=False),sa.Column('day',sa.Date(),index=True),
        sa.Column('place_id',sa.Uuid(as_uuid=False),sa.ForeignKey('places.id',ondelete='RESTRICT'),index=True),
        sa.Column('city',sa.String(100),nullable=False),sa.Column('city_source',sa.String(30),nullable=False),sa.Column('city_override',sa.String(100)),
        sa.Column('category',sa.String(100),nullable=False),sa.Column('active',sa.Boolean(),nullable=False),sa.Column('revision',sa.Integer(),nullable=False),
        sa.UniqueConstraint('record_id','source_key',name='uq_food_occurrence_source'))
    op.create_index('ix_food_city_date','food_occurrences',['city','day'])

def downgrade():
    raise RuntimeError('拒绝删除v5组织数据，禁止自动降级；请在独立空环境恢复升级前保护包')
