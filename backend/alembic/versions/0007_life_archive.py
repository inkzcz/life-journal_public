"""Structured trips and photo annotations. No changes to existing rows or files."""
from alembic import op
import sqlalchemy as sa
revision='0007_life_archive'
down_revision='0006_content_templates'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('trip_plans',sa.Column('record_id',sa.Uuid(as_uuid=False),sa.ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True),sa.Column('start_date',sa.Date(),nullable=True),sa.Column('end_date',sa.Date(),nullable=True),sa.Column('map_mode',sa.String(12),nullable=False),sa.CheckConstraint("map_mode IN ('offline','hidden')",name='ck_trip_map_mode'),sa.CheckConstraint('start_date IS NULL OR end_date IS NULL OR start_date <= end_date',name='ck_trip_dates'))
    op.create_table('trip_activities',sa.Column('id',sa.Uuid(as_uuid=False),primary_key=True),sa.Column('record_id',sa.Uuid(as_uuid=False),sa.ForeignKey('content_records.id',ondelete='RESTRICT'),nullable=False),sa.Column('day',sa.Date(),nullable=False),sa.Column('time',sa.String(5),nullable=True),sa.Column('title',sa.String(200),nullable=False),sa.Column('description',sa.Text(),nullable=False),sa.Column('place_id',sa.Uuid(as_uuid=False),sa.ForeignKey('places.id',ondelete='RESTRICT'),nullable=True),sa.Column('position',sa.Integer(),nullable=False),sa.Column('active',sa.Boolean(),nullable=False),sa.CheckConstraint('position >= 0',name='ck_trip_activity_position'))
    op.create_index('ix_trip_activities_record_id','trip_activities',['record_id'])
    op.create_index('ix_trip_activities_day','trip_activities',['day'])
    op.create_table('trip_activity_media',sa.Column('activity_id',sa.Uuid(as_uuid=False),sa.ForeignKey('trip_activities.id',ondelete='RESTRICT'),primary_key=True),sa.Column('media_id',sa.Uuid(as_uuid=False),sa.ForeignKey('media_assets.id',ondelete='RESTRICT'),primary_key=True),sa.Column('active',sa.Boolean(),nullable=False))
    op.create_index('ix_trip_activity_media_media_id','trip_activity_media',['media_id'])
    op.create_table('photo_annotations',sa.Column('record_id',sa.Uuid(as_uuid=False),sa.ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True),sa.Column('media_id',sa.Uuid(as_uuid=False),sa.ForeignKey('media_assets.id',ondelete='RESTRICT'),primary_key=True),sa.Column('taken_on',sa.Date(),nullable=True),sa.Column('place_id',sa.Uuid(as_uuid=False),sa.ForeignKey('places.id',ondelete='RESTRICT'),nullable=True),sa.Column('group_name',sa.String(100),nullable=False),sa.Column('active',sa.Boolean(),nullable=False))
    op.create_index('ix_photo_annotations_media_id','photo_annotations',['media_id'])

def downgrade():
    raise RuntimeError('拒绝删除行程、照片元数据和历史引用；关闭动态功能并保留0007数据库，参阅Phase 3F回滚指南')
