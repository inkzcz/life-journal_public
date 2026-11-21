"""Additive template identities, immutable versions and explicit record bindings."""
from sqlalchemy import String, Text, Boolean, Integer, Uuid, ForeignKey, ForeignKeyConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .content_models import json_type

class ContentTemplate(Base):
    __tablename__ = 'content_templates'
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default='')
    type_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey('content_types.id', ondelete='RESTRICT'), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (CheckConstraint('revision >= 1', name='ck_template_revision'),)

class TemplateVersion(Base):
    __tablename__ = 'template_versions'
    template_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey('content_templates.id', ondelete='RESTRICT'), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    type_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    schema_version: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict] = mapped_column(json_type)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'))
    __table_args__ = (ForeignKeyConstraint(['type_id', 'schema_version'], ['content_type_versions.type_id', 'content_type_versions.number'], ondelete='RESTRICT'),)

class RecordTemplate(Base):
    __tablename__ = 'record_templates'
    record_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey('content_records.id', ondelete='RESTRICT'), primary_key=True)
    template_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    version: Mapped[int] = mapped_column(Integer)
    __table_args__ = (ForeignKeyConstraint(['template_id', 'version'], ['template_versions.template_id', 'template_versions.number'], ondelete='RESTRICT'),)
