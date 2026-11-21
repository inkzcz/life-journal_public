"""Private inline media, preserving every old body and immutable snapshot."""
from alembic import op
import sqlalchemy as sa
revision='0011_immersive_writing'
down_revision='0010_media_readiness'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('content_records',sa.Column('body_format',sa.Integer(),nullable=False,server_default='1'))
    op.create_table('record_body_media',
        sa.Column('record_id',sa.Uuid(as_uuid=False),sa.ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('media_id',sa.Uuid(as_uuid=False),sa.ForeignKey('media_assets.id',ondelete='RESTRICT'),primary_key=True))
    op.create_index('ix_record_body_media_media_id','record_body_media',['media_id'])
    op.create_table('revision_media_refs',
        sa.Column('record_id',sa.Uuid(as_uuid=False),primary_key=True),sa.Column('number',sa.Integer(),primary_key=True),
        sa.Column('media_id',sa.Uuid(as_uuid=False),sa.ForeignKey('media_assets.id',ondelete='RESTRICT'),primary_key=True),
        sa.ForeignKeyConstraint(['record_id','number'],['record_revisions.record_id','record_revisions.number'],ondelete='RESTRICT'))
    op.create_index('ix_revision_media_refs_media_id','revision_media_refs',['media_id'])
    op.create_table('media_upload_operations',
        sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),sa.Column('uploaded_by',sa.Integer(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('request_key',sa.String(36),nullable=False),sa.Column('media_id',sa.Uuid(as_uuid=False),nullable=False),sa.Column('sha256',sa.String(64),nullable=False),
        sa.Column('state',sa.String(20),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('uploaded_by','request_key'),sa.CheckConstraint("state IN ('pending','completed')",name='ck_upload_operation_state'))
    # Bounded streaming backfill. Old snapshots stay byte-for-byte untouched.
    from app.services.body_media import referenced_ids
    con=op.get_bind()
    from uuid import UUID
    available=set(str(UUID(str(x))) for x in con.execute(sa.text('SELECT id FROM media_assets')).scalars())
    refs=sa.table('revision_media_refs',sa.column('record_id',sa.Uuid(as_uuid=False)),sa.column('number',sa.Integer()),sa.column('media_id',sa.Uuid(as_uuid=False)))
    for record_id,number,snapshot in con.execute(sa.text('SELECT record_id,number,snapshot FROM record_revisions')).yield_per(100):
        if isinstance(snapshot,str):
            import json
            snapshot=json.loads(snapshot)
        rows=[{'record_id':str(record_id),'number':number,'media_id':id} for id in referenced_ids(snapshot) if id in available]
        if rows:con.execute(refs.insert(),rows)

def downgrade():
    raise RuntimeError('拒绝删除正文及历史引用；请前向修复或将升级前完整备份恢复到独立目标')
