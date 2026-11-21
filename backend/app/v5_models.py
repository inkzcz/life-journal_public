"""Additive logical organization; no ownership of physical media or Markdown."""
from datetime import datetime, date
from sqlalchemy import String, Text, Integer, Boolean, Date, DateTime, Uuid, ForeignKey, UniqueConstraint, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import now
from .content_models import json_type

class RecordMediaFolder(Base):
    __tablename__='record_media_folders'
    record_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True)
    folder_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('media_folders.id',ondelete='RESTRICT'),unique=True)

class MediaArchiveRule(Base):
    __tablename__='media_archive_rules'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    name:Mapped[str]=mapped_column(String(100))
    enabled:Mapped[bool]=mapped_column(Boolean,default=False)
    date_source:Mapped[str]=mapped_column(String(20))
    fallback:Mapped[str]=mapped_column(String(20))
    granularity:Mapped[str]=mapped_column(String(10))
    by_type:Mapped[bool]=mapped_column(Boolean,default=False)
    parent_id:Mapped[str|None]=mapped_column(Uuid(as_uuid=False),ForeignKey('media_folders.id',ondelete='RESTRICT'),nullable=True)
    revision:Mapped[int]=mapped_column(Integer,default=1)
    created_by:Mapped[int]=mapped_column(ForeignKey('users.id',ondelete='RESTRICT'))
    __table_args__=(CheckConstraint("date_source IN ('uploaded','captured')",name='ck_archive_source'),CheckConstraint("fallback IN ('uploaded','unknown')",name='ck_archive_fallback'),CheckConstraint("granularity IN ('year','month','day')",name='ck_archive_granularity'),)

class MediaArchivePlan(Base):
    __tablename__='media_archive_plans'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    rule_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('media_archive_rules.id',ondelete='RESTRICT'),index=True)
    rule_revision:Mapped[int]=mapped_column(Integer)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id',ondelete='RESTRICT'))
    items:Mapped[list]=mapped_column(json_type)
    completed:Mapped[bool]=mapped_column(Boolean,default=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class FoodContentType(Base):
    __tablename__='food_content_types'
    type_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('content_types.id',ondelete='RESTRICT'),primary_key=True)
    template_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('content_templates.id',ondelete='RESTRICT'),unique=True)

class FoodOccurrence(Base):
    __tablename__='food_occurrences'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    record_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('content_records.id',ondelete='RESTRICT'),index=True)
    source_key:Mapped[str]=mapped_column(String(160))
    source_kind:Mapped[str]=mapped_column(String(20))
    name:Mapped[str]=mapped_column(String(200))
    description:Mapped[str]=mapped_column(Text,default='')
    day:Mapped[date|None]=mapped_column(Date,nullable=True,index=True)
    place_id:Mapped[str|None]=mapped_column(Uuid(as_uuid=False),ForeignKey('places.id',ondelete='RESTRICT'),nullable=True,index=True)
    city:Mapped[str]=mapped_column(String(100),default='')
    city_source:Mapped[str]=mapped_column(String(30),default='unknown')
    city_override:Mapped[str|None]=mapped_column(String(100),nullable=True)
    category:Mapped[str]=mapped_column(String(100),default='')
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    revision:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(UniqueConstraint('record_id','source_key',name='uq_food_occurrence_source'),Index('ix_food_city_date','city','day'),)
