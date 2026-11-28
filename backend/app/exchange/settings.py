"""Revisioned provider metadata and writing rules; secrets stay in server env."""
import re,uuid
from typing import Literal
from uuid import UUID
from urllib.parse import urlsplit,urlunsplit
from pydantic import Field,field_validator,model_validator
from sqlalchemy import select
from fastapi import HTTPException
from ..archive_schemas import StrictModel
from ..blog_models import SiteConfig
from ..services.archive import write_lock
from ..services.write_barrier import writer
from .rules import Preferences

KEY='ai-writing'
SLUG=re.compile(r'^[a-z][a-z0-9_-]{0,79}$')


def endpoint(value):
    if len(value)>500 or any(ord(c)<33 for c in value):raise ValueError('端点地址无效')
    try:
        parsed=urlsplit(value)
        if parsed.scheme not in {'https','http'} or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
            raise ValueError('端点仅允许无凭据、查询和片段的HTTP(S)地址')
        if parsed.port is not None and not 1<=parsed.port<=65535:raise ValueError('端点端口无效')
        host=parsed.hostname.encode('idna').decode('ascii').lower()
        if not re.fullmatch(r'[a-z0-9.:-]+',host) or host.endswith('.'):raise ValueError('端点主机名无效')
        if not re.fullmatch(r'/[a-zA-Z0-9/_-]*',parsed.path or '/'):raise ValueError('端点路径无效')
        bracket='['+host+']' if ':' in host else host
        netloc=bracket+(':'+str(parsed.port) if parsed.port is not None else '')
        return urlunsplit((parsed.scheme,netloc,parsed.path.rstrip('/'),'',''))
    except (ValueError,UnicodeError):raise ValueError('端点格式无效，不允许凭据、编码路径或控制字符') from None


class Provider(StrictModel):
    id:UUID
    name:str=Field(min_length=1,max_length=80)
    kind:Literal['openai','ollama','anthropic','gemini']
    base_url:str=Field(max_length=500)
    model:str=Field(min_length=1,max_length=200)
    key_env:str|None=Field(None,pattern=r'^LJ_AI_KEY_[A-Z0-9_]{1,80}$')
    enabled:bool=False
    service_id:UUID|None=None
    text:bool=True
    reasoning:bool=False
    json_mode:bool=True
    token_parameter:Literal['auto','max_tokens','max_completion_tokens','omit']='auto'
    system_role:Literal['system','developer']='system'
    vision:bool=False
    max_output_tokens:int=Field(2048,ge=64,le=16384,strict=True)
    daily_requests:int=Field(20,ge=1,le=1000,strict=True)
    timeout_seconds:int=Field(60,ge=5,le=120,strict=True)
    _endpoint=field_validator('base_url')(endpoint)
    @model_validator(mode='after')
    def safe_metadata(self):
        if any(ord(c)<32 for c in self.name+self.model):raise ValueError('名称或模型包含控制字符')
        if self.kind in {'openai','anthropic','gemini'} and not self.key_env and self.service_id is None:raise ValueError('云端模型必须指定LJ_AI_KEY_环境变量引用，不接收明文密钥')
        return self


# Existing provider UUIDs remain model profile identities for invocation history.
# Services are additive JSON metadata, never a new secret store or SQL table.
TASKS=('generate','polish','expand','continue','title','summary','tags','fields','trip','review')

class Service(StrictModel):
    id:UUID
    name:str=Field(min_length=1,max_length=80)
    kind:Literal['openai','ollama','anthropic','gemini']
    base_url:str=Field(max_length=500)
    key_env:str|None=Field(None,pattern=r'^LJ_AI_KEY_[A-Z0-9_]{1,80}$')
    enabled:bool=False
    timeout_seconds:int=Field(60,ge=5,le=120,strict=True)
    _endpoint=field_validator('base_url')(endpoint)
    @model_validator(mode='after')
    def valid(self):
        if any(ord(c)<32 for c in self.name):raise ValueError('名称包含控制字符')
        if self.kind!='ollama' and not self.key_env:raise ValueError('云端服务必须指定密钥环境变量引用')
        return self


class RuleScopes(StrictModel):
    global_preferences:dict=Field(default_factory=dict,max_length=20)
    content_types:dict[str,dict]=Field(default_factory=dict,max_length=100)
    templates:dict[str,dict]=Field(default_factory=dict,max_length=100)
    @model_validator(mode='after')
    def validate_layers(self):
        Preferences.model_validate(self.global_preferences)
        for table in (self.content_types,self.templates):
            for key,value in table.items():
                if not SLUG.fullmatch(key):raise ValueError('规则作用域须使用稳定标识')
                Preferences.model_validate(value)
        return self


class Configuration(StrictModel):
    default_provider:UUID|None=None
    providers:list[Provider]=Field(default_factory=list,max_length=100)
    services:list[Service]=Field(default_factory=list,max_length=30)
    task_defaults:dict[str,UUID|None]=Field(default_factory=dict,max_length=10)
    rules:RuleScopes=Field(default_factory=RuleScopes)
    @model_validator(mode='after')
    def identities(self):
        if len({p.id for p in self.providers})!=len(self.providers):raise ValueError('模型配置身份重复')
        if len({s.id for s in self.services})!=len(self.services):raise ValueError('服务商身份重复')
        if any(p.service_id is not None and p.service_id not in {s.id for s in self.services} for p in self.providers):raise ValueError('模型所属服务商不存在')
        if any(key not in TASKS for key in self.task_defaults):raise ValueError('默认任务不存在')
        # Dangling defaults are intentionally retained and shown as affected;
        # never pick a replacement service when a model is removed/disabled.
        return self

    def effective(self,profile):
        if profile.service_id is None:return profile
        service=next(s for s in self.services if s.id==profile.service_id)
        return profile.model_copy(update={**service.model_dump(exclude={'id','name','enabled'}),'enabled':profile.enabled and service.enabled})

    def profiles(self):
        return [self.effective(p) for p in self.providers]


def read(db):
    row=db.scalar(select(SiteConfig).where(SiteConfig.key==KEY))
    return (row.revision,Configuration.model_validate(row.value)) if row else (0,Configuration())


def save(db,value,expected_revision):
    with writer(db.bind):
        write_lock(db)
        row=db.scalar(select(SiteConfig).where(SiteConfig.key==KEY).with_for_update())
        if (row.revision if row else 0)!=expected_revision:raise HTTPException(409,'AI与写作配置已被修改，请重新读取后保存')
        # Resolve allowlist/DNS before enabling. Transport rechecks and pins all
        # actual requests separately, so saving a URL never authorizes rebinding.
        from .transport import resolve_endpoint
        for provider in value.profiles():
            if provider.enabled:resolve_endpoint(provider)
        if row:
            row.value=value.model_dump(mode='json');row.revision+=1
        else:
            row=SiteConfig(id=str(uuid.uuid4()),key=KEY,value=value.model_dump(mode='json'),revision=1);db.add(row)
        db.commit()
        return {'revision':row.revision,**value.model_dump(mode='json')}


def layers(db,type_slug,template_slug=None):
    _,config=read(db)
    return (config.rules.global_preferences,config.rules.content_types.get(type_slug,{}),config.rules.templates.get(template_slug,{}))
