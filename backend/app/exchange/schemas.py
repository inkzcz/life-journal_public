"""Versioned transport identities are not database identities or schema versions."""
from datetime import date
from typing import Annotated,Any,Literal
from uuid import UUID
from pydantic import Field,model_validator,field_validator
from ..archive_schemas import StrictModel
from ..life_schemas import canonical_date
from .rules import Preferences

Key = str
class Media(StrictModel):
    key:str=Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')
    path:str|None=Field(None,max_length=240)
    existing_id:UUID|None=None
    alt:str=Field('',max_length=1000)
    caption:str=Field('',max_length=2000)
    width:int=Field(960,ge=120,le=1600,strict=True)
    widthPercent:Literal[30,60,100]|None=None
    align:Literal['left','center','right']='center'
    layout:Literal['auto','single','grid']='auto'
    @model_validator(mode='after')
    def source(self):
        if (self.path is None)==(self.existing_id is None):raise ValueError('媒体需且只能指定包内path或现有existing_id')
        return self

class Place(StrictModel):
    key:str=Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')
    kind:Literal['l','f','s','h','t','c','p']='l'
    name:str=Field(min_length=1,max_length=200)
    existing_id:UUID|None=None
    city:str=Field('',max_length=100)
    address:str=Field('',max_length=500)

class Food(StrictModel):
    _date=field_validator('day',mode='before')(canonical_date)
    place_key:str=Field(max_length=64)
    day:date|None=None
    time:str|None=Field(None,pattern=r'^([01][0-9]|2[0-3]):[0-5][0-9]$')
    review:str=Field('',max_length=10000)
    media_keys:list[str]=Field(default_factory=list,max_length=100)

class Photo(StrictModel):
    _date=field_validator('taken_on',mode='before')(canonical_date)
    media_key:str=Field(max_length=64)
    taken_on:date|None=None
    place_key:str|None=Field(None,max_length=64)
    group_name:str=Field('',max_length=100)

class Activity(StrictModel):
    _date=field_validator('day',mode='before')(canonical_date)
    key:str=Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')
    day:date
    time:str|None=Field(None,pattern=r'^([01][0-9]|2[0-3]):[0-5][0-9]$')
    kind:Literal['food','sight','transport','other']='other'
    title:str=Field(min_length=1,max_length=200)
    description:str=Field('',max_length=10000)
    place_key:str|None=Field(None,max_length=64)
    media_keys:list[str]=Field(default_factory=list,max_length=100)

class Travel(StrictModel):
    _dates=field_validator('start_date','end_date',mode='before')(canonical_date)
    start_date:date|None=None
    end_date:date|None=None
    activities:list[Activity]=Field(default_factory=list,max_length=300)
    @model_validator(mode='after')
    def dates(self):
        if self.start_date and self.end_date and self.start_date>self.end_date:raise ValueError('旅行开始日期不能晚于结束日期')
        if len({a.key for a in self.activities})!=len(self.activities):raise ValueError('活动key重复')
        for a in self.activities:
            if self.start_date and a.day<self.start_date or self.end_date and a.day>self.end_date:raise ValueError('活动日期超出旅行范围')
        return self

class Link(StrictModel):
    record_key:str|None=None
    existing_id:UUID|None=None
    label:str=Field(min_length=1,max_length=80)
    @model_validator(mode='after')
    def source(self):
        if (self.record_key is None)==(self.existing_id is None):raise ValueError('关系需指定一个目标')
        return self

class Record(StrictModel):
    _date=field_validator('display_date',mode='before')(canonical_date)
    key:str=Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')
    type_slug:str=Field(pattern=r'^[a-z][a-z0-9_-]{0,79}$')
    schema_version:int|None=Field(None,ge=1)
    template_slug:str|None=Field(None,pattern=r'^[a-z][a-z0-9_-]{0,79}$')
    template_version:int|None=Field(None,ge=1)
    title:str=Field(min_length=1,max_length=200)
    body:str=Field('',max_length=300000)
    summary:str=Field('',max_length=500)
    display_date:date|None=None
    tags:list[Annotated[str,Field(min_length=1,max_length=40)]]=Field(default_factory=list,max_length=10)
    values:dict[str,Any]=Field(default_factory=dict,max_length=50)
    travel:Travel|None=None
    foods:list[Food]=Field(default_factory=list,max_length=100)
    photos:list[Photo]=Field(default_factory=list,max_length=100)
    cover_key:str|None=None
    media_keys:list[str]=Field(default_factory=list,max_length=100)
    links:list[Link]=Field(default_factory=list,max_length=100)

class Exchange(StrictModel):
    format:Literal['life-journal.exchange']
    version:Literal[1]
    records:list[Record]=Field(min_length=1,max_length=20)
    media:list[Media]=Field(default_factory=list,max_length=100)
    places:list[Place]=Field(default_factory=list,max_length=100)
    preferences:dict=Field(default_factory=dict,max_length=20,json_schema_extra=lambda schema:schema.update({'properties':Preferences.model_json_schema()['properties'],'additionalProperties':False}))
    @field_validator('version',mode='before')
    @classmethod
    def exact_version(cls,value):
        if type(value) is not int:raise ValueError('格式版本需为整数')
        return value
    @model_validator(mode='after')
    def references(self):
        from .rules import Preferences
        Preferences.model_validate(self.preferences)
        for rows in (self.records,self.media,self.places):
            if len({x.key for x in rows})!=len(rows):raise ValueError('key重复')
        paths=[x.path.casefold() for x in self.media if x.path]
        if len(paths)!=len(set(paths)):raise ValueError('同一照片只能声明一次，通过key显式复用')
        media={x.key for x in self.media};places={x.key for x in self.places};records={x.key for x in self.records}
        for r in self.records:
            mids=list(r.media_keys)+([r.cover_key] if r.cover_key else [])+[p.media_key for p in r.photos]
            pids=[p.place_key for p in r.photos if p.place_key]
            for f in r.foods:
                mids+=f.media_keys;pids.append(f.place_key)
                p=next((p for p in self.places if p.key==f.place_key),None)
                if p and p.kind!='f':raise ValueError('餐厅引用必须对应f类型地点')
            for a in r.travel.activities if r.travel else []:
                mids+=a.media_keys
                if a.place_key:pids.append(a.place_key)
            if set(mids)-media or set(pids)-places:raise ValueError('媒体或地点key不存在')
            if any(l.record_key and (l.record_key not in records or l.record_key==r.key) for l in r.links):raise ValueError('关联记录key无效或自关联')
        return self
