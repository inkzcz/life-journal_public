"""Maintenance jobs/catalog only; existing records and files remain intact."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='0008_recovery'
down_revision='0007_life_archive'
branch_labels=None
depends_on=None

def upgrade():
    data=sa.JSON().with_variant(JSONB(),'postgresql')
    op.create_table('maintenance_jobs',sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),sa.Column('kind',sa.String(20),nullable=False),sa.Column('state',sa.String(20),nullable=False),sa.Column('requested_by',sa.Integer(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=True),sa.Column('artifact_id',sa.Uuid(as_uuid=False),nullable=True),sa.Column('dedupe_key',sa.String(128),unique=True,nullable=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('started_at',sa.DateTime(timezone=True),nullable=True),sa.Column('finished_at',sa.DateTime(timezone=True),nullable=True),sa.Column('result',data,nullable=False),sa.Column('error',sa.String(200),nullable=False))
    op.create_index('ix_maintenance_jobs_kind','maintenance_jobs',['kind'])
    op.create_index('ix_maintenance_jobs_state','maintenance_jobs',['state'])
    op.create_table('backup_artifacts',sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('size',sa.BigInteger(),nullable=False),sa.Column('file_count',sa.BigInteger(),nullable=False),sa.Column('manifest_sha256',sa.String(64),nullable=False),sa.Column('app_version',sa.String(100),nullable=False),sa.Column('schema_version',sa.String(40),nullable=False),sa.Column('verified_at',sa.DateTime(timezone=True),nullable=True),sa.Column('restored_at',sa.DateTime(timezone=True),nullable=True))
    op.create_index('ix_content_records_deleted_at','content_records',['deleted_at'])

def downgrade():
    raise RuntimeError('拒绝删除：保留维护记录和备份验证证据；停止维护服务，使用兼容0008的回滚镜像或前向修复，勿删除表或恢复旧数据覆盖新记录')
