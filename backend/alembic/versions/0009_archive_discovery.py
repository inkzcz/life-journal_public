"""Add shared tag identities without rewriting legacy spellings or revision snapshots."""
import uuid
import unicodedata
from alembic import op
import sqlalchemy as sa
revision='0009_archive_discovery'
down_revision='0008_recovery'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('tags',sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),sa.Column('name',sa.String(40),nullable=False),sa.Column('normalized_name',sa.String(160),nullable=False,unique=True),sa.Column('merged_into',sa.Uuid(as_uuid=False),sa.ForeignKey('tags.id',ondelete='RESTRICT'),nullable=True),sa.Column('deleted_at',sa.DateTime(timezone=True),nullable=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('record_tags',sa.Column('record_id',sa.Uuid(as_uuid=False),sa.ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True),sa.Column('tag_id',sa.Uuid(as_uuid=False),sa.ForeignKey('tags.id',ondelete='RESTRICT'),primary_key=True))
    op.create_index('ix_record_tags_tag_record','record_tags',['tag_id','record_id'])
    op.create_table('journal_tag_identities',sa.Column('journal_id',sa.Integer(),primary_key=True),sa.Column('name',sa.String(40),primary_key=True),sa.Column('tag_id',sa.Uuid(as_uuid=False),sa.ForeignKey('tags.id',ondelete='RESTRICT'),nullable=False),sa.ForeignKeyConstraint(['journal_id','name'],['journal_tags.journal_id','journal_tags.name'],ondelete='CASCADE'))
    op.create_index('ix_journal_tag_identities_tag_id','journal_tag_identities',['tag_id'])
    op.create_index('ix_content_records_discovery_order','content_records',['status','display_date','id'])
    db=op.get_bind();catalog={}
    for jid,name in db.execute(sa.text('SELECT journal_id,name FROM journal_tags ORDER BY journal_id,name')).all():
        key=' '.join(unicodedata.normalize('NFKC',name).split()).casefold()
        if key not in catalog:
            id=str(uuid.uuid4());catalog[key]=id
            db.execute(sa.text('INSERT INTO tags(id,name,normalized_name,created_at,updated_at) VALUES(:id,:name,:key,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)'),{'id':id.replace('-','') if db.dialect.name=='sqlite' else id,'name':name,'key':key})
        db.execute(sa.text('INSERT INTO journal_tag_identities(journal_id,name,tag_id) VALUES(:jid,:name,:id)'),{'jid':jid,'name':name,'id':catalog[key].replace('-','') if db.dialect.name=='sqlite' else catalog[key]})
    before=db.scalar(sa.text('SELECT COUNT(*) FROM journal_tags'))
    after=db.scalar(sa.text('SELECT COUNT(*) FROM journal_tag_identities'))
    if before!=after:raise RuntimeError('旧标签映射数量不一致，停止升级')

def downgrade():
    raise RuntimeError('拒绝删除：标签身份及修订可能已被使用，禁止破坏性降级；请使用兼容0009镜像或前向修复，灾难恢复须恢复到隔离的新数据库和媒体目录')
