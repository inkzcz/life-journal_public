from typing import Annotated,Literal
from uuid import UUID
from pydantic import Field,model_validator,field_validator
from .archive_schemas import StrictModel
Layout=Literal['feature','grid2','grid3','list']
class SectionIn(StrictModel):
    name:str=Field(min_length=1,max_length=100)
    slug:str=Field(pattern=r'^[a-z][a-z0-9_-]{0,79}$')
    description:str=Field(default='',max_length=10000)
    cover_id:UUID|None=None
    position:int=Field(default=0,ge=0,le=10000)
    active:bool=True
    layout:Layout='grid2'
    type_ids:list[UUID]=Field(default_factory=list,max_length=100)
    @field_validator('name')
    @classmethod
    def valid_name(cls,v):
        if not v.strip():raise ValueError('名称不能为空')
        return v.strip()
    @model_validator(mode='after')
    def unique(self):
        if len(self.type_ids)!=len(set(self.type_ids)):raise ValueError('类型重复')
        return self
class SectionEdit(SectionIn):
    expected_revision:int=Field(ge=1)
Theme=Literal['modern','default','editorial','soft','glass','celadon']
Style=Literal['modern-flat','editorial','modern-soft','glass']
PaletteName=Literal['celadon','lilac']
ColorMode=Literal['light','dark']
ColorKey=Literal['page_background','card_background','body_text','heading_text','muted_text',
                 'nav_background','nav_text','link','primary_background','primary_text',
                 'secondary_background','secondary_text','tag_background','tag_text','border','accent']
# A finite schema: no CSS expressions, alpha channels, URLs or arbitrary properties.
HexColor=Annotated[str,Field(strict=True,min_length=7,max_length=7,pattern=r'^#[0-9a-fA-F]{6}$')]
class Appearance(StrictModel):
    theme:Theme='celadon'
    style:Style|None=None
    palette:PaletteName|None=None
    combination_colors:dict[Style,dict[PaletteName,dict[ColorMode,dict[ColorKey,HexColor]]]]=Field(default_factory=dict)
    mode:Literal['light','dark','system']='system'
    colors:dict[Theme,dict[ColorMode,dict[ColorKey,HexColor]]]=Field(default_factory=dict)
class AppearanceEdit(Appearance):
    expected_revision:int=Field(ge=0)
class Module(StrictModel):
    id:UUID
    kind:Literal['hero','featured','latest','section','gallery','text','anniversary_calendar']
    enabled:bool=True
    title:str=Field(default='',max_length=200)
    text:str=Field(default='',max_length=10000)
    count:int=Field(default=6,ge=1,le=24)
    layout:Layout='grid2'
    horizon:int=Field(30,ge=0,le=366)
    show_countdown:bool=True
    show_years:bool=True
    section_id:UUID|None=None
    type_id:UUID|None=None
    record_mode:Literal['daily','travel']|None=None
    record_ids:list[UUID]=Field(default_factory=list,max_length=24)
    @model_validator(mode='after')
    def valid(self):
        if self.kind=='section' and self.section_id is None:raise ValueError('栏目模块需要选择栏目')
        if len(set(self.record_ids))!=len(self.record_ids):raise ValueError('精选记录不能重复')
        return self
class LayoutIn(StrictModel):
    title:str=Field(default='Life Journal',min_length=1,max_length=100)
    description:str=Field(default='收藏日常，留住时光。',max_length=2000)
    modules:list[Module]=Field(default_factory=list,max_length=30)
    @model_validator(mode='after')
    def unique(self):
        if len({m.id for m in self.modules})!=len(self.modules):raise ValueError('模块标识重复')
        return self
class LayoutEdit(LayoutIn):
    expected_revision:int=Field(ge=0)
class NavItem(StrictModel):
    id:UUID
    parent_id:UUID|None=None
    name:str=Field(min_length=1,max_length=100)
    kind:Literal['home','section','record','page']
    section_id:UUID|None=None
    record_id:UUID|None=None
    page:Literal['journals','sections','stories','about','food','movies','shows','gifts','transport','photos','calendar','trips','places']|None=None
    active:bool=True
    @model_validator(mode='after')
    def target(self):
        if not self.name.strip():raise ValueError('导航名称不能为空')
        expected={'section':'section_id','record':'record_id','page':'page'}.get(self.kind)
        for k in ['section_id','record_id','page']:
            if (getattr(self,k) is not None)!=(k==expected):raise ValueError('导航目标不匹配')
        return self
class NavEdit(StrictModel):
    expected_revision:int=Field(ge=0)
    items:list[NavItem]=Field(default_factory=list,max_length=50)
    @model_validator(mode='after')
    def tree(self):
        ids={x.id:x for x in self.items}
        if len(ids)!=len(self.items):raise ValueError('导航标识重复')
        for x in self.items:
            if x.parent_id:
                parent=ids.get(x.parent_id)
                if parent is None or parent.id==x.id or parent.parent_id is not None:raise ValueError('导航只支持两级，禁止循环和无效父级')
        return self

class Typography(StrictModel):
    editor_line:Literal[1.0,1.25,1.5,1.75,2.0]=1.5
    editor_gap:Literal[0,4,8,12,16]=8
    # None preserves the pre-v5.1 reading defaults, including mobile rules.
    reader_line:Literal[1.0,1.25,1.5,1.75,2.0]|None=None
    reader_gap:Literal[0,4,8,12,16]|None=None
    @field_validator('editor_line','editor_gap','reader_line','reader_gap',mode='before')
    @classmethod
    def numeric_only(cls,v):
        if v is not None and type(v) not in (int,float):raise ValueError('排版值必须为白名单数字')
        return v
class TypographyEdit(Typography):
    expected_revision:int=Field(ge=0)
