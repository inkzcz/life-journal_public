"""Add editable templates without touching existing content or configuration."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='0006_content_templates'
down_revision='0005_blog_presentation'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('content_templates',
        sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),
        sa.Column('slug',sa.String(80),nullable=False,unique=True),
        sa.Column('name',sa.String(100),nullable=False),
        sa.Column('description',sa.Text(),nullable=False),
        sa.Column('type_id',sa.Uuid(as_uuid=False),sa.ForeignKey('content_types.id',ondelete='RESTRICT'),nullable=False,unique=True),
        sa.Column('active',sa.Boolean(),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),
        sa.CheckConstraint('revision >= 1',name='ck_template_revision'))
    op.create_table('template_versions',
        sa.Column('template_id',sa.Uuid(as_uuid=False),sa.ForeignKey('content_templates.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('number',sa.Integer(),primary_key=True),
        sa.Column('type_id',sa.Uuid(as_uuid=False),nullable=False),
        sa.Column('schema_version',sa.Integer(),nullable=False),
        sa.Column('config',sa.JSON().with_variant(postgresql.JSONB(),'postgresql'),nullable=False),
        sa.Column('created_by',sa.Integer(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.ForeignKeyConstraint(['type_id','schema_version'],['content_type_versions.type_id','content_type_versions.number'],ondelete='RESTRICT'))
    op.create_table('record_templates',
        sa.Column('record_id',sa.Uuid(as_uuid=False),sa.ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('template_id',sa.Uuid(as_uuid=False),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.ForeignKeyConstraint(['template_id','version'],['template_versions.template_id','template_versions.number'],ondelete='RESTRICT'))
    op.create_index('ix_record_templates_template_id','record_templates',['template_id'])

def downgrade():
    raise RuntimeError('拒绝删除模板与历史绑定；关闭动态功能并保留0006数据库，参阅Phase 3E回滚指南')
