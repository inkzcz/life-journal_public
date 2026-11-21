"""Structured extensions of records; all history and private resources are retained."""
from datetime import date
from decimal import Decimal
from sqlalchemy import Uuid, ForeignKey, String, Text, Date, Integer, Boolean, CheckConstraint, Numeric, Index, text
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base

class TripPlan(Base):
    __tablename__='trip_plans'
    record_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True)
    start_date:Mapped[date|None]=mapped_column(Date,nullable=True)
    end_date:Mapped[date|None]=mapped_column(Date,nullable=True)
    map_mode:Mapped[str]=mapped_column(String(12),default='offline')
    __table_args__=(CheckConstraint("map_mode IN ('offline','hidden')",name='ck_trip_map_mode'),CheckConstraint('start_date IS NULL OR end_date IS NULL OR start_date <= end_date',name='ck_trip_dates'))

class TripActivity(Base):
    __tablename__='trip_activities'
    __mapper_args__={'eager_defaults':False}
    markdown_owned:Mapped[bool]=mapped_column(Boolean,server_default=text('false'),deferred=True)
    kind:Mapped[str]=mapped_column(String(12),server_default='other',deferred=True,deferred_group='activity_details')
    dish:Mapped[str]=mapped_column(String(200),server_default='',deferred=True,deferred_group='activity_details')
    price:Mapped[Decimal|None]=mapped_column(Numeric(12,2),nullable=True,server_default=text('NULL'),deferred=True,deferred_group='activity_details')
    currency:Mapped[str]=mapped_column(String(3),server_default='',deferred=True,deferred_group='activity_details')
    rating:Mapped[int|None]=mapped_column(Integer,nullable=True,server_default=text('NULL'),deferred=True,deferred_group='activity_details')
    experience:Mapped[str]=mapped_column(Text,server_default='',deferred=True,deferred_group='activity_details')
    source_key:Mapped[str|None]=mapped_column(String(64),nullable=True,server_default=text('NULL'),deferred=True,deferred_group='activity_details')
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    record_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('content_records.id',ondelete='RESTRICT'),index=True)
    day:Mapped[date]=mapped_column(Date,index=True)
    time:Mapped[str|None]=mapped_column(String(5),nullable=True)
    title:Mapped[str]=mapped_column(String(200))
    description:Mapped[str]=mapped_column(Text,default='')
    place_id:Mapped[str|None]=mapped_column(Uuid(as_uuid=False),ForeignKey('places.id',ondelete='RESTRICT'),nullable=True)
    position:Mapped[int]=mapped_column(Integer)
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    __table_args__=(CheckConstraint('position >= 0',name='ck_trip_activity_position'),
        Index('uq_trip_activity_source','record_id','source_key',unique=True,postgresql_where=text('source_key IS NOT NULL'),sqlite_where=text('source_key IS NOT NULL')),
        CheckConstraint("kind IN ('food','sight','transport','other')",name='ck_activity_kind').ddl_if(dialect='postgresql'),
        CheckConstraint('price >= 0',name='ck_activity_price').ddl_if(dialect='postgresql'),
        CheckConstraint('rating BETWEEN 0 AND 5',name='ck_activity_rating').ddl_if(dialect='postgresql'))

class ActivityMedia(Base):
    __tablename__='trip_activity_media'
    activity_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('trip_activities.id',ondelete='RESTRICT'),primary_key=True)
    media_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('media_assets.id',ondelete='RESTRICT'),primary_key=True,index=True)
    active:Mapped[bool]=mapped_column(Boolean,default=True)

class PhotoAnnotation(Base):
    __tablename__='photo_annotations'
    record_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True)
    media_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('media_assets.id',ondelete='RESTRICT'),primary_key=True,index=True)
    taken_on:Mapped[date|None]=mapped_column(Date,nullable=True)
    place_id:Mapped[str|None]=mapped_column(Uuid(as_uuid=False),ForeignKey('places.id',ondelete='RESTRICT'),nullable=True)
    group_name:Mapped[str]=mapped_column(String(100),default='')
    active:Mapped[bool]=mapped_column(Boolean,default=True)
