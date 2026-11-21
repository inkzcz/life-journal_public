"""Add presentation configuration without changing content or old migrations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='0005_blog_presentation'
down_revision='0004_archive_resources'
branch_labels=None
depends_on=None

def upgrade():

    op.create_table('site_configs',
    sa.Column('id', sa.Uuid(as_uuid=False), nullable=False),
    sa.Column('key', sa.String(length=20), nullable=False),
    sa.Column('value', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.CheckConstraint('revision >= 1', name='ck_site_config_revision'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    op.create_table('sections',
    sa.Column('id', sa.Uuid(as_uuid=False), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('cover_id', sa.Uuid(as_uuid=False), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('layout', sa.String(length=20), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('revision >= 1', name='ck_section_revision'),
    sa.ForeignKeyConstraint(['cover_id'], ['media_assets.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('navigation_items',
    sa.Column('id', sa.Uuid(as_uuid=False), nullable=False),
    sa.Column('parent_id', sa.Uuid(as_uuid=False), nullable=True),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('section_id', sa.Uuid(as_uuid=False), nullable=True),
    sa.Column('record_id', sa.Uuid(as_uuid=False), nullable=True),
    sa.Column('page', sa.String(length=20), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['parent_id'], ['navigation_items.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['record_id'], ['content_records.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['section_id'], ['sections.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('section_content_types',
    sa.Column('section_id', sa.Uuid(as_uuid=False), nullable=False),
    sa.Column('type_id', sa.Uuid(as_uuid=False), nullable=False),
    sa.ForeignKeyConstraint(['section_id'], ['sections.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['type_id'], ['content_types.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('section_id', 'type_id')
    )
    op.create_index(op.f('ix_section_content_types_type_id'), 'section_content_types', ['type_id'], unique=False)


def downgrade():
    raise RuntimeError("拒绝删除栏目、导航、布局和外观；关闭功能并保留0005数据库，参阅Phase 3D回滚指南")
