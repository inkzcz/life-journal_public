"""Only declarative, bounded configuration; no executable markup or styles."""
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from .content_schemas import StrictModel, FieldIn

class TemplateField(StrictModel):
    key: UUID
    group: str = Field('基本信息', max_length=100)
    field: FieldIn

class DisplayModule(StrictModel):
    id: UUID
    kind: Literal['header','summary','body','fields','gallery','timeline','related','itinerary','map','album','life_timeline']
    title: str = Field('', max_length=100)
    enabled: bool = True
    layout: Literal['grid','masonry','large','card','date'] = 'grid'
    group_by: Literal['none','manual','date','place'] = 'none'
    field_ids: list[UUID] = Field(default_factory=list, max_length=50)

class TemplateIn(StrictModel):
    slug: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,79}$')
    name: str = Field(min_length=1, max_length=100)
    description: str = Field('', max_length=2000)
    active: bool = True
    expected_type_revision: int | None = Field(None, ge=1)
    fields: list[TemplateField] = Field(default_factory=list, max_length=50)
    modules: list[DisplayModule] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def check(self):
        if not self.name.strip(): raise ValueError('模板名称不能为空')
        keys={str(f.key):f for f in self.fields}
        if len(keys)!=len(self.fields): raise ValueError('字段标识重复')
        if len({m.id for m in self.modules})!=len(self.modules): raise ValueError('模块标识重复')
        for f in self.fields:
            if f.field.id and f.key!=f.field.id: raise ValueError('已有字段必须使用稳定标识')
        for m in self.modules:
            if len(set(m.field_ids))!=len(m.field_ids): raise ValueError('重复字段绑定')
            if any(str(id) not in keys for id in m.field_ids): raise ValueError('模块绑定未知字段')
            if m.kind not in {'summary','fields','timeline'} and m.field_ids: raise ValueError('此模块不支持字段绑定')
            if m.kind=='timeline' and any(keys[str(id)].field.kind!='date' for id in m.field_ids): raise ValueError('时间线只能绑定日期字段')
        return self

class TemplateUpdate(TemplateIn):
    expected_revision: int = Field(ge=1)

class TemplateCopy(StrictModel):
    slug: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,79}$')
    name: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=1)
