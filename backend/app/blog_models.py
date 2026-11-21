"""Presentation identities never alter content identities or field versions."""
from datetime import datetime
from sqlalchemy import String,Text,Integer,Boolean,Uuid,ForeignKey,DateTime,JSON,CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
from .models import now

class Section(Base):
    __tablename__='sections'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    name:Mapped[str]=mapped_column(String(100))
    slug:Mapped[str]=mapped_column(String(80),unique=True)
    description:Mapped[str]=mapped_column(Text,default='')
    cover_id:Mapped[str|None]=mapped_column(Uuid(as_uuid=False),ForeignKey('media_assets.id',ondelete='RESTRICT'),nullable=True)
    position:Mapped[int]=mapped_column(Integer,default=0)
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    layout:Mapped[str]=mapped_column(String(20),default='grid2')
    revision:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(CheckConstraint('revision >= 1',name='ck_section_revision'),)

class SectionType(Base):
    __tablename__='section_content_types'
    section_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('sections.id',ondelete='RESTRICT'),primary_key=True)
    type_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('content_types.id',ondelete='RESTRICT'),primary_key=True,index=True)

class SiteConfig(Base):
    __tablename__='site_configs'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    key:Mapped[str]=mapped_column(String(20),unique=True)
    value:Mapped[dict]=mapped_column(JSON().with_variant(JSONB(),'postgresql'))
    revision:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(CheckConstraint('revision >= 1',name='ck_site_config_revision'),)

class NavigationItem(Base):
    __tablename__='navigation_items'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    parent_id:Mapped[str|None]=mapped_column(Uuid(as_uuid=False),ForeignKey('navigation_items.id',ondelete='RESTRICT'),nullable=True)
    name:Mapped[str]=mapped_column(String(100))
    kind:Mapped[str]=mapped_column(String(20))
    section_id:Mapped[str|None]=mapped_column(Uuid(as_uuid=False),ForeignKey('sections.id',ondelete='RESTRICT'),nullable=True)
    record_id:Mapped[str|None]=mapped_column(Uuid(as_uuid=False),ForeignKey('content_records.id',ondelete='RESTRICT'),nullable=True)
    page:Mapped[str|None]=mapped_column(String(20),nullable=True)
    position:Mapped[int]=mapped_column(Integer)
    active:Mapped[bool]=mapped_column(Boolean,default=True)
