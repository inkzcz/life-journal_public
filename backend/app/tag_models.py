"""Stable shared tag identities; legacy spellings remain owned by journal_tags."""
from datetime import datetime
from sqlalchemy import String, Uuid, ForeignKey, ForeignKeyConstraint, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import now

class Tag(Base):
    __tablename__='tags'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    name:Mapped[str]=mapped_column(String(40))
    normalized_name:Mapped[str]=mapped_column(String(160),unique=True)
    merged_into:Mapped[str|None]=mapped_column(Uuid(as_uuid=False),ForeignKey('tags.id',ondelete='RESTRICT'),nullable=True)
    deleted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class RecordTag(Base):
    __tablename__='record_tags'
    record_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True)
    tag_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('tags.id',ondelete='RESTRICT'),primary_key=True)
    __table_args__=(Index('ix_record_tags_tag_record','tag_id','record_id'),)

class JournalTagIdentity(Base):
    __tablename__='journal_tag_identities'
    journal_id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(40),primary_key=True)
    tag_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('tags.id',ondelete='RESTRICT'),index=True)
    __table_args__=(ForeignKeyConstraint(['journal_id','name'],['journal_tags.journal_id','journal_tags.name'],ondelete='CASCADE'),)
