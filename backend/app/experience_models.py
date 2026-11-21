"""Stable source identities; entries and files never become duplicate articles."""
from datetime import date, datetime
from sqlalchemy import Uuid, ForeignKey, String, Date, DateTime, Boolean, Integer, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from . import life_models
from . import archive_models  # Register referenced media tables for standalone migration check.
from .content_models import json_type
from .models import now

class ArticleOptions(Base):
    __tablename__ = 'article_options'
    record_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey('content_records.id', ondelete='RESTRICT'), primary_key=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    travel_enabled: Mapped[bool] = mapped_column(Boolean)

class Experience(Base):
    __tablename__ = 'experiences'
    record_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey('content_records.id', ondelete='RESTRICT'), primary_key=True)
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    kind: Mapped[str] = mapped_column(String(1), index=True)
    name: Mapped[str] = mapped_column(String(200))
    fields: Mapped[dict] = mapped_column(json_type)
    position: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (CheckConstraint("kind IN ('l','f','m','s','g','t')", name='ck_experience_kind'),)

from sqlalchemy import ForeignKeyConstraint
class ExperienceMedia(Base):
    __tablename__ = 'experience_media'
    record_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    entry_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    media_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey('media_assets.id', ondelete='RESTRICT'), primary_key=True, index=True)
    position: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean)
    __table_args__ = (ForeignKeyConstraint(['record_id','entry_id'],['experiences.record_id','experiences.id'],ondelete='RESTRICT'),)

class ActivityExperience(Base):
    __tablename__='activity_experiences'
    activity_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('trip_activities.id',ondelete='RESTRICT'),primary_key=True)
    record_id:Mapped[str]=mapped_column(Uuid(as_uuid=False))
    entry_id:Mapped[str]=mapped_column(Uuid(as_uuid=False))
    __table_args__=(ForeignKeyConstraint(['record_id','entry_id'],['experiences.record_id','experiences.id'],ondelete='RESTRICT'),)
