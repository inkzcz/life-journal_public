"""Add versioned dynamic content; no legacy ALTER, backfill or media operations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0003_dynamic_content'
down_revision = '0002_admin_users'
branch_labels = None
depends_on = None


def upgrade():
    uid = sa.Uuid(as_uuid=False)
    js = sa.JSON().with_variant(JSONB(), 'postgresql')
    op.create_table('content_types',
        sa.Column('id',uid,primary_key=True), sa.Column('slug',sa.String(80),nullable=False,unique=True),
        sa.Column('name',sa.String(100),nullable=False), sa.Column('description',sa.Text(),nullable=False),
        sa.Column('active',sa.Boolean(),nullable=False), sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.CheckConstraint('revision >= 1',name='ck_content_type_revision'))
    op.create_table('content_type_versions',
        sa.Column('type_id',uid,sa.ForeignKey('content_types.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('number',sa.Integer(),primary_key=True),
        sa.Column('created_by',sa.Integer(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('field_definitions',
        sa.Column('id',uid,primary_key=True),sa.Column('type_id',uid,sa.ForeignKey('content_types.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('kind',sa.String(20),nullable=False),sa.UniqueConstraint('id','type_id',name='uq_field_identity_type'))
    op.create_table('version_fields',
        sa.Column('type_id',uid,primary_key=True),sa.Column('version',sa.Integer(),primary_key=True),
        sa.Column('field_id',uid,primary_key=True),sa.Column('name',sa.String(100),nullable=False),
        sa.Column('description',sa.Text(),nullable=False),sa.Column('position',sa.Integer(),nullable=False),
        sa.Column('required',sa.Boolean(),nullable=False),sa.Column('active',sa.Boolean(),nullable=False),
        sa.Column('has_default',sa.Boolean(),nullable=False),sa.Column('default_value',js,nullable=True),
        sa.Column('rules',js,nullable=False),
        sa.ForeignKeyConstraint(['type_id','version'],['content_type_versions.type_id','content_type_versions.number'],ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['field_id','type_id'],['field_definitions.id','field_definitions.type_id'],ondelete='RESTRICT'),
        sa.UniqueConstraint('type_id','version','position',name='uq_version_field_position'))
    op.create_table('content_records',
        sa.Column('id',uid,primary_key=True),sa.Column('type_id',uid,nullable=False),sa.Column('schema_version',sa.Integer(),nullable=False),
        sa.Column('title',sa.String(200),nullable=False),sa.Column('body',sa.Text(),nullable=False),
        sa.Column('display_date',sa.Date(),nullable=False),sa.Column('status',sa.String(12),nullable=False),
        sa.Column('values',js,nullable=False),sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('deleted_at',sa.DateTime(timezone=True),nullable=True),
        sa.ForeignKeyConstraint(['type_id','schema_version'],['content_type_versions.type_id','content_type_versions.number'],ondelete='RESTRICT'),
        sa.CheckConstraint("status IN ('draft','published')",name='ck_content_record_status'),
        sa.CheckConstraint('revision >= 1',name='ck_content_record_revision'))
    op.create_index('ix_content_records_type_id','content_records',['type_id'])
    op.create_index('ix_content_records_display_date','content_records',['display_date'])
    op.create_table('record_revisions',
        sa.Column('record_id',uid,sa.ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('number',sa.Integer(),primary_key=True),sa.Column('snapshot',js,nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))


def downgrade():
    raise RuntimeError('拒绝删除动态内容与历史版本；请关闭功能开关并保留数据库，参阅Phase 3B回滚说明')
