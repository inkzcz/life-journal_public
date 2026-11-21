from typing import Literal
from datetime import date
from uuid import UUID
from decimal import Decimal
from pydantic import Field, field_validator, model_validator
from pydantic import BaseModel, ConfigDict

class StrictModel(BaseModel):
    model_config=ConfigDict(extra='forbid')

class AssetEdit(StrictModel):
    category:str|None=Field(default=None,max_length=100)
    expected_revision:int=Field(ge=1)
    title:str=Field(default='',max_length=200)
    description:str=Field(default='',max_length=10000)
    alt:str=Field(default='',max_length=1000)

class PlaceIn(StrictModel):
    name:str=Field(min_length=1,max_length=200)
    country:str=Field(default='',max_length=100)
    region:str=Field(default='',max_length=100)
    city:str=Field(default='',max_length=100)
    address:str=Field(default='',max_length=500)
    category:str=Field(default='',max_length=100)
    notes:str=Field(default='',max_length=10000)
    latitude:Decimal|None=Field(default=None,ge=-90,le=90,decimal_places=6,allow_inf_nan=False)
    longitude:Decimal|None=Field(default=None,ge=-180,le=180,decimal_places=6,allow_inf_nan=False)
    active:bool=True
    @field_validator('name')
    @classmethod
    def name_valid(cls,v):
        if not v.strip():raise ValueError('地点名称不能为空')
        return v.strip()
    @model_validator(mode='after')
    def pair(self):
        if (self.latitude is None)!=(self.longitude is None):raise ValueError('经纬度需同时填写或同时留空')
        return self

class PlaceEdit(PlaceIn):
    expected_revision:int=Field(ge=1)

class MediaRef(StrictModel):
    id:UUID
    cover:bool=False
    caption:str=Field(default='',max_length=2000)

class LinkRef(StrictModel):
    id:UUID
    label:str=Field(min_length=1,max_length=80)
    @field_validator('label')
    @classmethod
    def label_valid(cls,v):
        if not v.strip():raise ValueError('关系名称不能为空')
        return ' '.join(v.split())

class Connections(StrictModel):
    media:list[MediaRef]=Field(default_factory=list,max_length=100)
    links:list[LinkRef]=Field(default_factory=list,max_length=100)
    places:list[UUID]=Field(default_factory=list,max_length=100)
    @model_validator(mode='after')
    def unique(self):
        for ids in [[str(x.id) for x in self.media],[(str(x.id),x.label) for x in self.links],[str(x) for x in self.places]]:
            if len(ids)!=len(set(ids)):raise ValueError('不能重复关联')
        if sum(x.cover for x in self.media)>1:raise ValueError('最多设置一张封面')
        return self


class FolderIn(StrictModel):
    name:str=Field(min_length=1,max_length=100)
    parent_id:UUID|None=None
    @field_validator('name')
    @classmethod
    def clean(cls,v):
        if not v.strip():raise ValueError('文件夹名称不能为空')
        return v.strip()
class FolderEdit(FolderIn):
    expected_revision:int=Field(ge=1)
class BatchItem(StrictModel):
    id:UUID
    expected_revision:int=Field(ge=1)
class MediaBatch(StrictModel):
    items:list[BatchItem]=Field(min_length=1,max_length=100)
    action:Literal['move','category','trash']
    folder_id:UUID|None=None
    category:str=Field(default='',max_length=100)
    confirmation:Literal['执行批量操作']
    @model_validator(mode='after')
    def unique(self):
        if len({i.id for i in self.items})!=len(self.items):raise ValueError('图片重复')
        return self
