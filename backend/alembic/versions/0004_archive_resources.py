"""Independent archive resources and relationships; additive only."""
from alembic import op
import sqlalchemy as sa
revision='0004_archive_resources'
down_revision='0003_dynamic_content'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('places',
    sa.Column('id', sa.Uuid(as_uuid=False), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('country', sa.String(length=100), nullable=False),
    sa.Column('region', sa.String(length=100), nullable=False),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('address', sa.String(length=500), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('latitude', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('longitude', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('(latitude IS NULL) = (longitude IS NULL)', name='ck_place_coordinates'),
    sa.CheckConstraint('latitude BETWEEN -90 AND 90', name='ck_place_latitude'),
    sa.CheckConstraint('longitude BETWEEN -180 AND 180', name='ck_place_longitude'),
    sa.CheckConstraint('revision >= 1', name='ck_place_revision'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_places_name'), 'places', ['name'], unique=False)
    op.create_table('media_assets',
    sa.Column('id', sa.Uuid(as_uuid=False), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('mime_type', sa.String(length=40), nullable=False),
    sa.Column('size', sa.BigInteger(), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('preview_sha256', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('alt', sa.String(length=1000), nullable=False),
    sa.Column('uploaded_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('revision >= 1', name='ck_asset_revision'),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_media_assets_created_at'), 'media_assets', ['created_at'], unique=False)
    op.create_table('record_links',
    sa.Column('source_id', sa.Uuid(as_uuid=False), nullable=False),
    sa.Column('target_id', sa.Uuid(as_uuid=False), nullable=False),
    sa.Column('label', sa.String(length=80), nullable=False),
    sa.CheckConstraint('source_id <> target_id', name='ck_record_link_not_self'),
    sa.ForeignKeyConstraint(['source_id'], ['content_records.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['target_id'], ['content_records.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('source_id', 'target_id', 'label')
    )
    op.create_index(op.f('ix_record_links_target_id'), 'record_links', ['target_id'], unique=False)
    op.create_table('record_media',
    sa.Column('record_id', sa.Uuid(as_uuid=False), nullable=False),
    sa.Column('media_id', sa.Uuid(as_uuid=False), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('cover', sa.Boolean(), nullable=False),
    sa.Column('caption', sa.String(length=2000), nullable=False),
    sa.CheckConstraint('position >= 0', name='ck_record_media_position'),
    sa.ForeignKeyConstraint(['media_id'], ['media_assets.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['record_id'], ['content_records.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('record_id', 'media_id'),
    sa.UniqueConstraint('record_id', 'position', name='uq_record_media_position')
    )
    op.create_index(op.f('ix_record_media_media_id'), 'record_media', ['media_id'], unique=False)
    op.create_index('uq_record_media_cover', 'record_media', ['record_id'], unique=True, postgresql_where=sa.text('cover'), sqlite_where=sa.text('cover = 1'))
    op.create_table('record_places',
    sa.Column('record_id', sa.Uuid(as_uuid=False), nullable=False),
    sa.Column('place_id', sa.Uuid(as_uuid=False), nullable=False),
    sa.ForeignKeyConstraint(['place_id'], ['places.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['record_id'], ['content_records.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('record_id', 'place_id')
    )
    op.create_index(op.f('ix_record_places_place_id'), 'record_places', ['place_id'], unique=False)

def downgrade():
    raise RuntimeError("拒绝删除媒体、地点与关联；关闭功能并保留0004数据库，参阅Phase 3C升级说明")
