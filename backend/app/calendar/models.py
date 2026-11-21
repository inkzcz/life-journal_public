from datetime import date,datetime
from sqlalchemy import Uuid,ForeignKey,String,Integer,Date,DateTime,UniqueConstraint,CheckConstraint,Boolean
from sqlalchemy.orm import Mapped,mapped_column
from ..db import Base
from ..content_models import json_type
from ..models import now
class Anniversary(Base):
    __tablename__='anniversaries'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    name:Mapped[str]=mapped_column(String(200))
    kind:Mapped[str]=mapped_column(String(20))
    rule:Mapped[dict]=mapped_column(json_type)
    reminders:Mapped[dict]=mapped_column(json_type)
    memories:Mapped[list]=mapped_column(json_type)
    active:Mapped[bool]=mapped_column(Boolean)
    revision:Mapped[int]=mapped_column(Integer)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Reminder(Base):
    __tablename__='anniversary_reminders'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    anniversary_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('anniversaries.id',ondelete='RESTRICT'),index=True)
    occurrence:Mapped[date]=mapped_column(Date)
    offset:Mapped[int]=mapped_column(Integer)
    channel:Mapped[str]=mapped_column(String(80))
    state:Mapped[str]=mapped_column(String(20))
    planned_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    attempted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    sent_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    retry_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    lease_until:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    attempts:Mapped[int]=mapped_column(Integer)
    http_status:Mapped[int|None]=mapped_column(Integer,nullable=True)
    error:Mapped[str]=mapped_column(String(80))
    __table_args__=(UniqueConstraint('anniversary_id','occurrence','offset','channel',name='uq_anniversary_reminder_node'),CheckConstraint("state IN ('queued','sending','sent','retry','failed','uncertain','cancelled')",name='ck_reminder_state'))
