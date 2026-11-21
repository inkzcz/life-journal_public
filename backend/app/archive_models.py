"""Independent archive resources; no relationship cascades or legacy media reuse."""
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Text, Integer, BigInteger, Boolean, Numeric, Date, DateTime, Uuid, ForeignKey, ForeignKeyConstraint, CheckConstraint, UniqueConstraint, Index, text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import now
from .content_models import json_type

class MediaAsset(Base):
    __tablename__='media_assets'
    __mapper_args__={'eager_defaults':False}
    captured_on:Mapped[date|None]=mapped_column(Date,nullable=True,server_default=text('NULL'),deferred=True,deferred_group='media_management')
    preview_width:Mapped[int|None]=mapped_column(Integer,nullable=True,server_default=text('NULL'))
    preview_height:Mapped[int|None]=mapped_column(Integer,nullable=True,server_default=text('NULL'))
    thumbnail_sha256:Mapped[str|None]=mapped_column(String(64),nullable=True,server_default=text('NULL'))
    folder_id:Mapped[str|None]=mapped_column(Uuid(as_uuid=False),ForeignKey('media_folders.id'),nullable=True,server_default=text('NULL'),deferred=True,deferred_group='media_management',index=True)
    purge_operation_id:Mapped[str|None]=mapped_column(Uuid(as_uuid=False),nullable=True,server_default=text('NULL'),deferred=True,deferred_group='media_management')
    category:Mapped[str]=mapped_column(String(100),server_default='',deferred=True,deferred_group='media_management')
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    filename:Mapped[str]=mapped_column(String(255))
    mime_type:Mapped[str]=mapped_column(String(40))
    size:Mapped[int]=mapped_column(BigInteger)
    width:Mapped[int]=mapped_column(Integer)
    height:Mapped[int]=mapped_column(Integer)
    sha256:Mapped[str]=mapped_column(String(64))
    preview_sha256:Mapped[str]=mapped_column(String(64))
    title:Mapped[str]=mapped_column(String(200),default='')
    description:Mapped[str]=mapped_column(Text,default='')
    alt:Mapped[str]=mapped_column(String(1000),default='')
    uploaded_by:Mapped[int]=mapped_column(ForeignKey('users.id',ondelete='RESTRICT'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,index=True)
    revision:Mapped[int]=mapped_column(Integer,default=1)
    deleted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    __table_args__=(CheckConstraint('revision >= 1',name='ck_asset_revision'),Index('ix_media_assets_deleted_order','deleted_at','id'))

class Place(Base):
    __tablename__='places'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    name:Mapped[str]=mapped_column(String(200),index=True)
    country:Mapped[str]=mapped_column(String(100),default='')
    region:Mapped[str]=mapped_column(String(100),default='')
    city:Mapped[str]=mapped_column(String(100),default='')
    address:Mapped[str]=mapped_column(String(500),default='')
    category:Mapped[str]=mapped_column(String(100),default='')
    notes:Mapped[str]=mapped_column(Text,default='')
    latitude:Mapped[Decimal|None]=mapped_column(Numeric(9,6),nullable=True)
    longitude:Mapped[Decimal|None]=mapped_column(Numeric(9,6),nullable=True)
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    revision:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(CheckConstraint('latitude BETWEEN -90 AND 90',name='ck_place_latitude'),CheckConstraint('longitude BETWEEN -180 AND 180',name='ck_place_longitude'),CheckConstraint('(latitude IS NULL) = (longitude IS NULL)',name='ck_place_coordinates'),CheckConstraint('revision >= 1',name='ck_place_revision'))

class RecordMedia(Base):
    __tablename__='record_media'
    record_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True)
    media_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('media_assets.id',ondelete='RESTRICT'),primary_key=True,index=True)
    position:Mapped[int]=mapped_column(Integer)
    cover:Mapped[bool]=mapped_column(Boolean,default=False)
    caption:Mapped[str]=mapped_column(String(2000),default='')
    __table_args__=(Index('uq_record_media_cover','record_id',unique=True,postgresql_where=text('cover'),sqlite_where=text('cover = 1')),UniqueConstraint('record_id','position',name='uq_record_media_position'),CheckConstraint('position >= 0',name='ck_record_media_position'))

class RecordLink(Base):
    __tablename__='record_links'
    source_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True)
    target_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True,index=True)
    label:Mapped[str]=mapped_column(String(80),primary_key=True)
    __table_args__=(CheckConstraint('source_id <> target_id',name='ck_record_link_not_self'),)

class RecordPlace(Base):
    __mapper_args__={'eager_defaults':False}
    __tablename__='record_places'
    markdown_owned:Mapped[bool]=mapped_column(Boolean,server_default=text('false'),deferred=True)
    record_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True)
    place_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('places.id',ondelete='RESTRICT'),primary_key=True,index=True)


class MediaUploadOperation(Base):
    """A durable upload identity, not an automatic task queue."""
    __tablename__='media_upload_operations'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    uploaded_by:Mapped[int]=mapped_column(ForeignKey('users.id',ondelete='RESTRICT'))
    request_key:Mapped[str]=mapped_column(String(36))
    media_id:Mapped[str]=mapped_column(Uuid(as_uuid=False))
    sha256:Mapped[str]=mapped_column(String(64))
    state:Mapped[str]=mapped_column(String(20),default='pending')
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(UniqueConstraint('uploaded_by','request_key'),CheckConstraint("state IN ('pending','completed')",name='ck_upload_operation_state'))


class MediaFolder(Base):
    __tablename__='media_folders'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    parent_id:Mapped[str|None]=mapped_column(Uuid(as_uuid=False),ForeignKey('media_folders.id',ondelete='RESTRICT'),nullable=True)
    name:Mapped[str]=mapped_column(String(100))
    normalized_name:Mapped[str]=mapped_column(String(100))
    revision:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(Index('uq_folder_parent_name','parent_id','normalized_name',unique=True,postgresql_where=text('parent_id IS NOT NULL'),sqlite_where=text('parent_id IS NOT NULL')),Index('uq_folder_root_name','normalized_name',unique=True,postgresql_where=text('parent_id IS NULL'),sqlite_where=text('parent_id IS NULL')),CheckConstraint('parent_id IS NULL OR parent_id <> id',name='ck_folder_not_self'),)

class MediaPurgeOperation(Base):
    __tablename__='media_purge_operations'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    media_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),index=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id',ondelete='RESTRICT'))
    request_key:Mapped[str]=mapped_column(String(36))
    state:Mapped[str]=mapped_column(String(20))
    manifest:Mapped[dict]=mapped_column(json_type)
    error_code:Mapped[str]=mapped_column(String(80),default='')
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(UniqueConstraint('actor_id','request_key'),CheckConstraint("state IN ('prepared','isolated','db_committed','completed','cancelled')",name='ck_media_purge_state'))

class ResourceReferenceAudit(Base):
    __tablename__='resource_reference_audits'
    key:Mapped[str]=mapped_column(String(40),primary_key=True)
    value:Mapped[dict]=mapped_column(json_type)

class PlaceAlias(Base):
    __tablename__='place_aliases'
    source_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('places.id',ondelete='RESTRICT'),primary_key=True)
    target_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('places.id',ondelete='RESTRICT'),index=True)
    __table_args__=(CheckConstraint('source_id <> target_id',name='ck_place_alias_self'),)

class RevisionPlaceRef(Base):
    __tablename__='revision_place_refs'
    record_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    number:Mapped[int]=mapped_column(Integer,primary_key=True)
    place_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('places.id',ondelete='RESTRICT'),primary_key=True,index=True)
    __table_args__=(ForeignKeyConstraint(['record_id','number'],['record_revisions.record_id','record_revisions.number'],ondelete='RESTRICT'),)

class RecordMarkedPlace(Base):
    __tablename__='record_marked_places'
    record_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('content_records.id',ondelete='RESTRICT'),primary_key=True)
    source_key:Mapped[str]=mapped_column(String(64),primary_key=True)
    place_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('places.id',ondelete='RESTRICT'),index=True)
