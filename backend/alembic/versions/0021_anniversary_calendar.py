"""Independent calendar and durable reminder nodes; no article rewrite."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='0021_anniversary_calendar'
down_revision='0020_photo_albums'
branch_labels=depends_on=None

def upgrade():
    js=sa.JSON().with_variant(JSONB(),'postgresql')
    op.create_table('anniversaries',sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),sa.Column('name',sa.String(200),nullable=False),sa.Column('kind',sa.String(20),nullable=False),sa.Column('rule',js,nullable=False),sa.Column('reminders',js,nullable=False),sa.Column('memories',js,nullable=False),sa.Column('active',sa.Boolean(),nullable=False),sa.Column('revision',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('anniversary_reminders',sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),sa.Column('anniversary_id',sa.Uuid(as_uuid=False),sa.ForeignKey('anniversaries.id',ondelete='RESTRICT'),nullable=False),sa.Column('occurrence',sa.Date(),nullable=False),sa.Column('offset',sa.Integer(),nullable=False),sa.Column('channel',sa.String(80),nullable=False),sa.Column('state',sa.String(20),nullable=False),sa.Column('planned_at',sa.DateTime(timezone=True),nullable=False),sa.Column('attempted_at',sa.DateTime(timezone=True),nullable=True),sa.Column('sent_at',sa.DateTime(timezone=True),nullable=True),sa.Column('retry_at',sa.DateTime(timezone=True),nullable=True),sa.Column('lease_until',sa.DateTime(timezone=True),nullable=True),sa.Column('attempts',sa.Integer(),nullable=False),sa.Column('http_status',sa.Integer(),nullable=True),sa.Column('error',sa.String(80),nullable=False),sa.UniqueConstraint('anniversary_id','occurrence','offset','channel',name='uq_anniversary_reminder_node'),sa.CheckConstraint("state IN ('queued','sending','sent','retry','failed','uncertain','cancelled')",name='ck_reminder_state'))
    op.create_index('ix_anniversary_reminders_anniversary_id','anniversary_reminders',['anniversary_id'])

def downgrade():
    raise RuntimeError('禁止删除纪念日和提醒发送记录；请在空目标恢复升级前备份')
