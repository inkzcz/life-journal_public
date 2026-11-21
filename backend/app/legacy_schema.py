"""Frozen Phase 2 baseline. Do not replace with evolving application models."""
from datetime import date, datetime, timezone
from sqlalchemy import String, Text, ForeignKey, DateTime, Integer, Date
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

def now(): return datetime.now(timezone.utc)
class User(Base):
    __tablename__='users'
    id: Mapped[int]=mapped_column(primary_key=True)
    username: Mapped[str]=mapped_column(String(100),unique=True)
    password_hash: Mapped[str]=mapped_column(Text)
class Session(Base):
    __tablename__='sessions'
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'))
    token_hash: Mapped[str]=mapped_column(String(64),unique=True,index=True)
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
class Journal(Base):
    __tablename__='journals'
    id: Mapped[int]=mapped_column(primary_key=True)
    title: Mapped[str]=mapped_column(String(200))
    content: Mapped[str]=mapped_column(Text,default='')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)
class Media(Base):
    __tablename__='media'
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    journal_id: Mapped[int]=mapped_column(ForeignKey('journals.id',ondelete='CASCADE'),index=True)
    filename: Mapped[str]=mapped_column(String(255))
    mime_type: Mapped[str]=mapped_column(String(50))


# Additive tables: existing journals and photos are never rewritten on upgrade.
class JournalMetadata(Base):
    __tablename__ = 'journal_metadata'
    journal_id: Mapped[int] = mapped_column(ForeignKey('journals.id', ondelete='CASCADE'), primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(80), default='', index=True)


class JournalTag(Base):
    __tablename__ = 'journal_tags'
    journal_id: Mapped[int] = mapped_column(ForeignKey('journals.id', ondelete='CASCADE'), primary_key=True)
    name: Mapped[str] = mapped_column(String(40), primary_key=True, index=True)

metadata = Base.metadata
