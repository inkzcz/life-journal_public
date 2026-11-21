"""Dynamic content identities and immutable schema versions; legacy tables are untouched."""
from datetime import date, datetime
from sqlalchemy import (String, Text, Integer, Boolean, Date, DateTime, JSON, Uuid,
                        ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import now

json_type = JSON().with_variant(JSONB(), 'postgresql')


class ContentType(Base):
    __tablename__ = 'content_types'
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default='')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (CheckConstraint('revision >= 1', name='ck_content_type_revision'),)


class ContentTypeVersion(Base):
    __tablename__ = 'content_type_versions'
    type_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey('content_types.id', ondelete='RESTRICT'), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FieldDefinition(Base):
    __tablename__ = 'field_definitions'
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    type_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey('content_types.id', ondelete='RESTRICT'))
    kind: Mapped[str] = mapped_column(String(20))
    __table_args__ = (UniqueConstraint('id', 'type_id', name='uq_field_identity_type'),)


class VersionField(Base):
    __tablename__ = 'version_fields'
    type_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default='')
    position: Mapped[int] = mapped_column(Integer)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    has_default: Mapped[bool] = mapped_column(Boolean, default=False)
    default_value: Mapped[object] = mapped_column(json_type, nullable=True)
    rules: Mapped[dict] = mapped_column(json_type, default=dict)
    __table_args__ = (
        ForeignKeyConstraint(['type_id','version'], ['content_type_versions.type_id','content_type_versions.number'], ondelete='RESTRICT'),
        ForeignKeyConstraint(['field_id','type_id'], ['field_definitions.id','field_definitions.type_id'], ondelete='RESTRICT'),
        UniqueConstraint('type_id','version','position',name='uq_version_field_position'),
    )


class ContentRecord(Base):
    __mapper_args__={'eager_defaults':False}
    __tablename__ = 'content_records'
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    type_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    schema_version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(String(500), server_default='', deferred=True)
    body_format: Mapped[int] = mapped_column(Integer, server_default='1', deferred=True)
    body: Mapped[str] = mapped_column(Text, default='')
    display_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(12), default='draft')
    values: Mapped[dict] = mapped_column(json_type, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True,index=True)
    __table_args__ = (
        ForeignKeyConstraint(['type_id','schema_version'], ['content_type_versions.type_id','content_type_versions.number'], ondelete='RESTRICT'),
        CheckConstraint("status IN ('draft','published')",name='ck_content_record_status'),
        CheckConstraint('revision >= 1',name='ck_content_record_revision'),
        Index('ix_records_active_order',display_date.desc(),id,postgresql_where=text('deleted_at IS NULL'),sqlite_where=text('deleted_at IS NULL')),
        Index('ix_content_records_discovery_order','status','display_date','id'),
    )


class RecordRevision(Base):
    __tablename__ = 'record_revisions'
    record_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey('content_records.id', ondelete='RESTRICT'), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot: Mapped[dict] = mapped_column(json_type)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RecordBodyMedia(Base):
    __tablename__ = 'record_body_media'
    record_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey('content_records.id', ondelete='RESTRICT'), primary_key=True)
    media_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey('media_assets.id', ondelete='RESTRICT'), primary_key=True, index=True)


class RevisionMediaRef(Base):
    __tablename__ = 'revision_media_refs'
    record_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey('media_assets.id', ondelete='RESTRICT'), primary_key=True, index=True)
    __table_args__ = (ForeignKeyConstraint(['record_id','number'], ['record_revisions.record_id','record_revisions.number'], ondelete='RESTRICT'),)
