"""Preview/confirmation journals and usage metadata; never parallel article storage."""
from datetime import datetime
from sqlalchemy import String,Integer,Boolean,DateTime,Uuid,ForeignKey,UniqueConstraint,CheckConstraint,Index
from sqlalchemy.orm import Mapped,mapped_column
from ..db import Base
from ..models import now
from ..content_models import json_type

class ExchangeJob(Base):
    __tablename__='exchange_jobs'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id',ondelete='RESTRICT'),index=True)
    request_key:Mapped[str]=mapped_column(Uuid(as_uuid=False))
    source_sha256:Mapped[str]=mapped_column(String(64))
    source_kind:Mapped[str]=mapped_column(String(20))
    state:Mapped[str]=mapped_column(String(20),default='preview')
    revision:Mapped[int]=mapped_column(Integer,default=1)
    payload:Mapped[dict]=mapped_column(json_type)
    context_digests:Mapped[dict]=mapped_column(json_type,default=dict)
    file_manifest:Mapped[dict]=mapped_column(json_type,default=dict)
    result_ids:Mapped[list]=mapped_column(json_type,default=list)
    error_code:Mapped[str]=mapped_column(String(80),default='')
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    __table_args__=(UniqueConstraint('actor_id','request_key',name='uq_exchange_actor_request'),CheckConstraint("state IN ('preview','confirming','completed','cancelled','failed')",name='ck_exchange_job_state'),CheckConstraint('revision >= 1',name='ck_exchange_job_revision'))

class ExchangeFileOperation(Base):
    __tablename__='exchange_file_operations'
    job_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('exchange_jobs.id',ondelete='RESTRICT'),primary_key=True)
    state:Mapped[str]=mapped_column(String(20))
    manifest:Mapped[dict]=mapped_column(json_type)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(CheckConstraint("state IN ('prepared','files_ready','db_committed','completed','rolled_back')",name='ck_exchange_file_state'),)

class AIInvocation(Base):
    __tablename__='ai_invocations'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id',ondelete='RESTRICT'))
    request_key:Mapped[str]=mapped_column(Uuid(as_uuid=False))
    provider_id:Mapped[str]=mapped_column(Uuid(as_uuid=False))
    config_revision:Mapped[int]=mapped_column(Integer)
    model:Mapped[str]=mapped_column(String(200))
    action:Mapped[str]=mapped_column(String(30))
    state:Mapped[str]=mapped_column(String(20))
    rules_digest:Mapped[str]=mapped_column(String(64))
    input_tokens:Mapped[int]=mapped_column(Integer,default=0)
    output_tokens:Mapped[int]=mapped_column(Integer,default=0)
    usage_known:Mapped[bool]=mapped_column(Boolean,default=False)
    error_code:Mapped[str]=mapped_column(String(80),default='')
    job_id:Mapped[str|None]=mapped_column(Uuid(as_uuid=False),ForeignKey('exchange_jobs.id',ondelete='RESTRICT'),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    finished_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    __table_args__=(UniqueConstraint('actor_id','request_key',name='uq_ai_actor_request'),CheckConstraint("state IN ('reserved','running','succeeded','failed','cancelled','unknown')",name='ck_ai_invocation_state'),CheckConstraint('input_tokens >= 0 AND output_tokens >= 0',name='ck_ai_usage_nonnegative'),Index('ix_ai_provider_time','provider_id','created_at'))
