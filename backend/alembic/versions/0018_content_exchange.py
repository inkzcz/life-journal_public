"""Add preview/confirmation journals and AI usage metadata; preserve all old rows."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='0018_content_exchange'
down_revision='0017_v5_organization'
branch_labels=None
depends_on=None


def upgrade():
    js=sa.JSON().with_variant(JSONB(),'postgresql')
    op.create_table('exchange_jobs',
        sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('request_key',sa.Uuid(as_uuid=False),nullable=False),
        sa.Column('source_sha256',sa.String(64),nullable=False),sa.Column('source_kind',sa.String(20),nullable=False),
        sa.Column('state',sa.String(20),nullable=False),sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('payload',js,nullable=False),sa.Column('context_digests',js,nullable=False),
        sa.Column('file_manifest',js,nullable=False),sa.Column('result_ids',js,nullable=False),
        sa.Column('error_code',sa.String(80),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('actor_id','request_key',name='uq_exchange_actor_request'),
        sa.CheckConstraint("state IN ('preview','confirming','completed','cancelled','failed')",name='ck_exchange_job_state'),
        sa.CheckConstraint('revision >= 1',name='ck_exchange_job_revision'))
    op.create_index('ix_exchange_jobs_actor_id','exchange_jobs',['actor_id'])
    op.create_table('exchange_file_operations',
        sa.Column('job_id',sa.Uuid(as_uuid=False),sa.ForeignKey('exchange_jobs.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('state',sa.String(20),nullable=False),sa.Column('manifest',js,nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.CheckConstraint("state IN ('prepared','files_ready','db_committed','completed','rolled_back')",name='ck_exchange_file_state'))
    op.create_table('ai_invocations',
        sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('request_key',sa.Uuid(as_uuid=False),nullable=False),sa.Column('provider_id',sa.Uuid(as_uuid=False),nullable=False),
        sa.Column('config_revision',sa.Integer(),nullable=False),sa.Column('model',sa.String(200),nullable=False),
        sa.Column('action',sa.String(30),nullable=False),sa.Column('state',sa.String(20),nullable=False),
        sa.Column('rules_digest',sa.String(64),nullable=False),sa.Column('input_tokens',sa.Integer(),nullable=False),
        sa.Column('output_tokens',sa.Integer(),nullable=False),sa.Column('usage_known',sa.Boolean(),nullable=False),
        sa.Column('error_code',sa.String(80),nullable=False),
        sa.Column('job_id',sa.Uuid(as_uuid=False),sa.ForeignKey('exchange_jobs.id',ondelete='RESTRICT'),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('finished_at',sa.DateTime(timezone=True),nullable=True),
        sa.UniqueConstraint('actor_id','request_key',name='uq_ai_actor_request'),
        sa.CheckConstraint("state IN ('reserved','running','succeeded','failed','cancelled','unknown')",name='ck_ai_invocation_state'),
        sa.CheckConstraint('input_tokens >= 0 AND output_tokens >= 0',name='ck_ai_usage_nonnegative'))
    op.create_index('ix_ai_provider_time','ai_invocations',['provider_id','created_at'])


def downgrade():
    raise RuntimeError('禁止自动删除交换任务、文件日志和AI用量记录；请在独立空目录恢复升级前保护包')
