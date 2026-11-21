"""Additive maintenance audit and backup catalog; no cascades into content."""
from datetime import datetime
from sqlalchemy import Uuid,String,Text,DateTime,ForeignKey,BigInteger,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
from .models import now
from .content_models import json_type

class MaintenanceJob(Base):
    __tablename__='maintenance_jobs'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    kind:Mapped[str]=mapped_column(String(20),index=True)
    state:Mapped[str]=mapped_column(String(20),default='queued',index=True)
    requested_by:Mapped[int|None]=mapped_column(ForeignKey('users.id',ondelete='RESTRICT'),nullable=True)
    artifact_id:Mapped[str|None]=mapped_column(Uuid(as_uuid=False),nullable=True)
    dedupe_key:Mapped[str|None]=mapped_column(String(128),unique=True,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    started_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    finished_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    result:Mapped[dict]=mapped_column(json_type,default=dict)
    error:Mapped[str]=mapped_column(String(200),default='')

class BackupArtifact(Base):
    __tablename__='backup_artifacts'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    size:Mapped[int]=mapped_column(BigInteger)
    file_count:Mapped[int]=mapped_column(BigInteger)
    manifest_sha256:Mapped[str]=mapped_column(String(64))
    app_version:Mapped[str]=mapped_column(String(100))
    schema_version:Mapped[str]=mapped_column(String(40))
    verified_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    restored_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
