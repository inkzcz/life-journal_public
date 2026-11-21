from datetime import time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo
from pydantic import Field,field_validator,model_validator
from ..content_schemas import StrictModel
from .dates import DateRule
class Reminders(StrictModel):
    enabled:bool=True
    on_day:bool=True
    offsets:list[int]=Field(default_factory=list,max_length=16)
    time:str|None=None
    @field_validator('offsets')
    @classmethod
    def offsets_valid(cls,v):
        if any(type(x)is not int or not 1<=x<=3660 for x in v) or len(set(v))!=len(v):raise ValueError('提前天数须为1–3660且不重复；当天提醒独立配置')
        return sorted(v)
    @field_validator('time')
    @classmethod
    def time_valid(cls,v):
        if v is not None and (len(v)!=5 or time.fromisoformat(v).second):raise ValueError('提醒时间使用HH:MM')
        return v
class EventIn(StrictModel):
    name:str=Field(min_length=1,max_length=200)
    kind:Literal['birthday','anniversary','important','once']='anniversary'
    rule:DateRule
    reminders:Reminders=Field(default_factory=Reminders)
    memories:list[UUID]=Field(default_factory=list,max_length=200)
    expected_revision:int=Field(0,ge=0)
    @model_validator(mode='after')
    def valid(self):
        if not self.name.strip():raise ValueError('名称不能为空')
        if len(set(self.memories))!=len(self.memories):raise ValueError('专属回忆重复')
        if self.kind=='once' and self.rule.repeat!='once':raise ValueError('一次性提醒须使用单次日期规则')
        return self
class NotifyConfig(StrictModel):
    enabled:bool=False
    url_template:str=Field('',max_length=4000)
    timezone:str='Asia/Shanghai'
    time:str='09:00'
    expected_revision:int=Field(0,ge=0)
    @field_validator('time')
    @classmethod
    def valid_time(cls,v):
        if len(v)!=5 or time.fromisoformat(v).second:raise ValueError('提醒时间使用HH:MM')
        return v
    @field_validator('timezone')
    @classmethod
    def valid_zone(cls,v):
        try:ZoneInfo(v)
        except (KeyError,ValueError):raise ValueError('时区必须是有效IANA名称') from None
        return v
