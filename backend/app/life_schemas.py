from datetime import date
from decimal import Decimal
from uuid import UUID
from typing import Literal
from pydantic import Field,field_validator,model_validator
from .archive_schemas import StrictModel

def canonical_date(v):
    if v is None or type(v) is date:return v
    if not isinstance(v,str) or date.fromisoformat(v).isoformat()!=v:raise ValueError('日期需使用YYYY-MM-DD')
    return v

class ActivityIn(StrictModel):
    experience_id:UUID|None=None
    _day=field_validator('day',mode='before')(canonical_date)
    kind:Literal['food','sight','transport','other']='other'
    dish:str=Field('',max_length=200)
    price:Decimal|None=Field(None,ge=0,max_digits=12,decimal_places=2,allow_inf_nan=False)
    currency:str=Field('',pattern=r'^(?:[A-Z]{3})?$')
    rating:int|None=Field(None,ge=0,le=5,strict=True)
    experience:str=Field('',max_length=10000)
    source_key:str|None=Field(None,pattern=r'^[a-f0-9]{64}$')
    id:UUID
    day:date
    time:str|None=Field(None,pattern=r'^([01][0-9]|2[0-3]):[0-5][0-9]$')
    title:str=Field(min_length=1,max_length=200)
    description:str=Field('',max_length=10000)
    place_id:UUID|None=None
    media_ids:list[UUID]=Field(default_factory=list,max_length=100)
    @field_validator('title')
    @classmethod
    def nonblank(cls,v):
        if not v.strip():raise ValueError('活动标题不能为空')
        return v.strip()
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.media_ids))!=len(self.media_ids):raise ValueError('活动图片不能重复')
        return self

class PhotoIn(StrictModel):
    _day=field_validator('taken_on',mode='before')(canonical_date)
    media_id:UUID
    taken_on:date|None=None
    place_id:UUID|None=None
    group_name:str=Field('',max_length=100)

class LifeIn(StrictModel):
    _dates=field_validator('start_date','end_date',mode='before')(canonical_date)
    start_date:date|None=None
    end_date:date|None=None
    map_mode:Literal['offline','hidden']='offline'
    activities:list[ActivityIn]=Field(default_factory=list,max_length=300)
    photos:list[PhotoIn]=Field(default_factory=list,max_length=100)
    @model_validator(mode='after')
    def valid(self):
        if self.start_date and self.end_date and self.start_date>self.end_date:raise ValueError('旅行结束日期不能早于开始日期')
        sources=[x.source_key for x in self.activities if x.source_key]
        if len(set(sources))!=len(sources):raise ValueError('来源活动重复')
        if len({x.id for x in self.activities})!=len(self.activities):raise ValueError('活动标识重复')
        if len({x.media_id for x in self.photos})!=len(self.photos):raise ValueError('照片信息重复')
        for a in self.activities:
            if self.start_date and a.day<self.start_date or self.end_date and a.day>self.end_date:raise ValueError('活动日期超出旅行范围')
        return self
