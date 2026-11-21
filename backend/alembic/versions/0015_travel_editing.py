"""Optional activity details; no separate food library, no old data rewrite."""
from alembic import op
import sqlalchemy as sa
revision='0015_travel_editing'
down_revision='0014_place_identity'
branch_labels=None
depends_on=None

def upgrade():
    for name,type_,nullable,default in [('kind',sa.String(12),False,'other'),('dish',sa.String(200),False,''),('price',sa.Numeric(12,2),True,None),('currency',sa.String(3),False,''),('rating',sa.Integer(),True,None),('experience',sa.Text(),False,''),('source_key',sa.String(64),True,None)]:
        op.add_column('trip_activities',sa.Column(name,type_,nullable=nullable,server_default=default))
    # Portable conditional unique index; unlimited NULL/manual activities.
    op.create_index('uq_trip_activity_source','trip_activities',['record_id','source_key'],unique=True,postgresql_where=sa.text('source_key IS NOT NULL'),sqlite_where=sa.text('source_key IS NOT NULL'))
    # Service validation remains canonical. PostgreSQL also protects direct writes.
    if op.get_bind().dialect.name=='postgresql':
        op.create_check_constraint('ck_activity_kind','trip_activities',"kind IN ('food','sight','transport','other')")
        op.create_check_constraint('ck_activity_price','trip_activities','price >= 0')
        op.create_check_constraint('ck_activity_rating','trip_activities','rating BETWEEN 0 AND 5')

def downgrade():raise RuntimeError('拒绝删除活动来源及用餐记录；请前向修复或独立目标恢复')
