"""Retain merged place identities and index immutable revision references."""
from alembic import op
import sqlalchemy as sa
revision='0014_place_identity'
down_revision='0013_media_recovery'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('place_aliases',
        sa.Column('source_id',sa.Uuid(as_uuid=False),sa.ForeignKey('places.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('target_id',sa.Uuid(as_uuid=False),sa.ForeignKey('places.id',ondelete='RESTRICT'),nullable=False),
        sa.CheckConstraint('source_id <> target_id',name='ck_place_alias_self'))
    op.create_index('ix_place_aliases_target_id','place_aliases',['target_id'])
    op.create_table('revision_place_refs',
        sa.Column('record_id',sa.Uuid(as_uuid=False),primary_key=True),sa.Column('number',sa.Integer(),primary_key=True),
        sa.Column('place_id',sa.Uuid(as_uuid=False),sa.ForeignKey('places.id',ondelete='RESTRICT'),primary_key=True),
        sa.ForeignKeyConstraint(['record_id','number'],['record_revisions.record_id','record_revisions.number'],ondelete='RESTRICT'))
    op.create_index('ix_revision_place_refs_place_id','revision_place_refs',['place_id'])
    from sqlalchemy.orm import Session
    from app.services.places import audit
    with Session(bind=op.get_bind()) as db:audit(db)

def downgrade():raise RuntimeError('拒绝删除地点历史身份与引用；请前向修复或恢复到独立目标')
