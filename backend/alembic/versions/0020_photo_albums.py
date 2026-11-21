"""Independent manual albums, referencing existing UUIDs only."""
from alembic import op
import sqlalchemy as sa
revision='0020_photo_albums'
down_revision='0019_unified_experiences'
branch_labels=depends_on=None

def upgrade():
    op.create_table('photo_albums',sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),sa.Column('name',sa.String(200),nullable=False),sa.Column('cover_id',sa.Uuid(as_uuid=False),sa.ForeignKey('media_assets.id',ondelete='RESTRICT'),nullable=True),sa.Column('revision',sa.Integer(),nullable=False))
    op.create_table('photo_album_photos',sa.Column('album_id',sa.Uuid(as_uuid=False),sa.ForeignKey('photo_albums.id',ondelete='RESTRICT'),primary_key=True),sa.Column('media_id',sa.Uuid(as_uuid=False),sa.ForeignKey('media_assets.id',ondelete='RESTRICT'),primary_key=True),sa.Column('position',sa.Integer(),nullable=False))
    op.create_index('ix_photo_album_photos_media_id','photo_album_photos',['media_id'])

def downgrade():
    raise RuntimeError('禁止删除手工相册；请在空目标恢复升级前备份')
