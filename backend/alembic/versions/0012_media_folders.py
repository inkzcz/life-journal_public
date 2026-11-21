"""Logical media organization, no filesystem changes."""
from alembic import op
import sqlalchemy as sa
revision='0012_media_folders'
down_revision='0011_immersive_writing'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('media_folders',sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),sa.Column('parent_id',sa.Uuid(as_uuid=False),sa.ForeignKey('media_folders.id',ondelete='RESTRICT'),nullable=True),sa.Column('name',sa.String(100),nullable=False),sa.Column('normalized_name',sa.String(100),nullable=False),sa.Column('revision',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),sa.CheckConstraint('parent_id IS NULL OR parent_id <> id',name='ck_folder_not_self'))
    for kind,predicate,columns in [('parent','parent_id IS NOT NULL',['parent_id','normalized_name']),('root','parent_id IS NULL',['normalized_name'])]:
        op.create_index('uq_folder_'+kind+'_name','media_folders',columns,unique=True,postgresql_where=sa.text(predicate),sqlite_where=sa.text(predicate))
    if op.get_bind().dialect.name=='sqlite':op.execute('ALTER TABLE media_assets ADD COLUMN folder_id CHAR(32) DEFAULT NULL REFERENCES media_folders(id)')
    else:op.add_column('media_assets',sa.Column('folder_id',sa.Uuid(as_uuid=False),sa.ForeignKey('media_folders.id'),nullable=True,server_default=sa.text('NULL')))
    op.add_column('media_assets',sa.Column('category',sa.String(100),nullable=False,server_default=''))
    op.create_index('ix_media_assets_folder_id','media_assets',['folder_id'])

def downgrade():raise RuntimeError('拒绝丢弃文件夹归属；请前向修复或从备份恢复到独立目标')
