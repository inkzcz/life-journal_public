"""A deliberately bounded configuration language, not executable expressions."""
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .archive_schemas import Connections

Kind = Literal['short_text','long_text','markdown','integer','decimal','date','select','multiselect']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Option(StrictModel):
    id: UUID
    label: str = Field(min_length=1,max_length=100)
    active: bool = True

    @field_validator('label')
    @classmethod
    def clean(cls,value):
        if not value.strip():
            raise ValueError('选项名称不能为空')
        return value.strip()


class Rules(StrictModel):
    min_length: int | None = Field(default=None,ge=0,le=300000)
    max_length: int | None = Field(default=None,ge=1,le=300000)
    min_value: Decimal | None = Field(default=None,allow_inf_nan=False,ge=-9007199254740991,le=9007199254740991)
    max_value: Decimal | None = Field(default=None,allow_inf_nan=False,ge=-9007199254740991,le=9007199254740991)
    min_date: date | None = None
    max_date: date | None = None
    options: list[Option] = Field(default_factory=list,max_length=50)
    max_items: int | None = Field(default=None,ge=1,le=50)


class FieldIn(StrictModel):
    purpose: Literal['food_shop','food_date','food_city','food_address','food_review'] | None = None
    id: UUID | None = None
    kind: Kind
    name: str = Field(min_length=1,max_length=100)
    description: str = Field(default='',max_length=2000)
    position: int = Field(ge=0,le=49)
    required: bool = False
    active: bool = True
    searchable: bool = False
    has_default: bool = False
    default_value: Any = None
    rules: Rules = Field(default_factory=Rules)

    @field_validator('name')
    @classmethod
    def clean_name(cls,value):
        if not value.strip():
            raise ValueError('字段名称不能为空')
        return value.strip()

    @model_validator(mode='after')
    def valid_rules(self):
        if self.searchable and self.kind not in {"short_text","long_text","markdown"}:
            raise ValueError("只有文本字段可以参与搜索")
        if self.purpose and self.kind not in ({'date'} if self.purpose=='food_date' else {'long_text','markdown'} if self.purpose=='food_review' else {'short_text'}):
            raise ValueError('美食字段语义与字段类型不匹配')
        r=self.rules
        permitted={
            'short_text':{'min_length','max_length'},'long_text':{'min_length','max_length'},
            'markdown':{'min_length','max_length'},'integer':{'min_value','max_value'},
            'decimal':{'min_value','max_value'},'date':{'min_date','max_date'},
            'select':{'options'},'multiselect':{'options','max_items'},
        }[self.kind]
        configured={k for k,v in r.model_dump().items() if v is not None and v!=[]}
        if configured-permitted:
            raise ValueError('该字段类型不支持这些验证规则')
        for low,high in [(r.min_length,r.max_length),(r.min_value,r.max_value),(r.min_date,r.max_date)]:
            if low is not None and high is not None and low>high:
                raise ValueError('最小值不能大于最大值')
        if self.kind=='short_text' and any(v is not None and v>1000 for v in [r.min_length,r.max_length]):
            raise ValueError('短文本最多1000字符')
        if self.kind=='integer' and any(v is not None and v!=v.to_integral_value() for v in [r.min_value,r.max_value]):
            raise ValueError('整数边界必须是整数')
        ids=[str(o.id) for o in r.options]
        if len(ids)!=len(set(ids)):
            raise ValueError('选项标识不能重复')
        if self.kind in {'select','multiselect'} and not r.options:
            raise ValueError('选择字段至少需要一个选项')
        if not self.has_default and self.default_value is not None:
            raise ValueError('未开启默认值，不能提交默认值')
        return self


class TypeCreate(StrictModel):
    slug: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,79}$')
    name: str = Field(min_length=1,max_length=100)
    description: str = Field(default='',max_length=2000)
    active: bool = True
    fields: list[FieldIn] = Field(default_factory=list,max_length=50)

    @field_validator('name')
    @classmethod
    def clean_name(cls,value):
        if not value.strip():
            raise ValueError('类型名称不能为空')
        return value.strip()

    @model_validator(mode='after')
    def unique_fields(self):
        purposes=[f.purpose for f in self.fields if f.purpose and f.active]
        if len(purposes)!=len(set(purposes)):raise ValueError('美食字段语义不能重复')
        positions=[f.position for f in self.fields]
        ids=[str(f.id) for f in self.fields if f.id is not None]
        if len(positions)!=len(set(positions)) or len(ids)!=len(set(ids)):
            raise ValueError('字段顺序和标识不能重复')
        return self


class TypeUpdate(TypeCreate):
    expected_revision: int = Field(ge=1)


class RecordTemplateIn(StrictModel):
    id: UUID
    version: int = Field(ge=1)


from .life_schemas import LifeIn

class ArticleOptionsIn(StrictModel):
    end_date: date | None = None
    travel_enabled: bool = False


class RecordIn(StrictModel):
    marker_version:Literal[1,2]=1
    article: ArticleOptionsIn | None = None
    new_media_ids: list[UUID] = Field(default_factory=list,max_length=100)
    tag_ids: list[UUID] | None = Field(default=None,max_length=10)
    life: LifeIn | None = None
    template: RecordTemplateIn | None = None
    connections: Connections | None = None
    schema_version: int = Field(ge=1)
    title: str = Field(min_length=1,max_length=200)
    summary: str | None = Field(default=None,max_length=500)
    body_format: Literal[1,2] | None = None
    body: str = Field(default='',max_length=300000)
    display_date: date
    status: Literal['draft','published'] = 'draft'
    values: dict[str,Any] = Field(default_factory=dict,max_length=50)

    @field_validator('marker_version',mode='before')
    @classmethod
    def marker_integer(cls,value):
        if type(value) is not int:raise ValueError('标记协议版本必须为整数')
        return value

    @field_validator('body_format',mode='before')
    @classmethod
    def format_integer(cls,value):
        if value is not None and type(value) is not int:raise ValueError('正文格式版本必须为整数')
        return value

    @field_validator('title')
    @classmethod
    def clean_title(cls,value):
        if not value.strip():
            raise ValueError('标题不能为空')
        return value.strip()


class RecordCreate(RecordIn):
    type_id: UUID


class RecordUpdate(RecordIn):
    expected_revision: int = Field(ge=1)


class DeleteIn(StrictModel):
    expected_revision: int = Field(ge=1)
