"""Durable media quarantine operations and conservative reference audit."""
from alembic import op
import sqlalchemy as sa
revision='0013_media_recovery'
down_revision='0012_media_folders'
branch_labels=None
depends_on=None

def upgrade():
    from sqlalchemy.dialects.postgresql import JSONB
    op.create_table('media_purge_operations',
        sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),
        sa.Column('media_id',sa.Uuid(as_uuid=False),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('request_key',sa.String(36),nullable=False),
        sa.Column('state',sa.String(20),nullable=False),
        sa.Column('manifest',sa.JSON().with_variant(JSONB(),'postgresql'),nullable=False),
        sa.Column('error_code',sa.String(80),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('actor_id','request_key'),
        sa.CheckConstraint("state IN ('prepared','isolated','db_committed','completed','cancelled')",name='ck_media_purge_state'))
    op.create_index('ix_media_purge_operations_media_id','media_purge_operations',['media_id'])
    op.create_table('resource_reference_audits',sa.Column('key',sa.String(40),primary_key=True),sa.Column('value',sa.JSON().with_variant(JSONB(),'postgresql'),nullable=False))
    op.add_column('media_assets',sa.Column('purge_operation_id',sa.Uuid(as_uuid=False),nullable=True,server_default=sa.text('NULL')))
    op.create_index('ix_media_assets_deleted_order','media_assets',['deleted_at','id'])
    from sqlalchemy.orm import Session
    from app.services.resource_usage import audit_media
    with Session(bind=op.get_bind()) as db:audit_media(db)

def downgrade():raise RuntimeError('拒绝删除日志与引用审计；请前向修复或将备份恢复到独立目标')
