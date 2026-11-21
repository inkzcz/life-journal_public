from typing import Literal
from uuid import UUID
from pydantic import Field,model_validator
from .archive_schemas import StrictModel
class RevisionIn(StrictModel):
    expected_revision:int=Field(ge=1)
class TrashItem(RevisionIn):
    id:UUID
class TrashBatch(StrictModel):
    items:list[TrashItem]=Field(min_length=1,max_length=100)
    confirmation:Literal['恢复','永久删除']
    @model_validator(mode='after')
    def unique(self):
        if len({x.id for x in self.items})!=len(self.items):raise ValueError('记录重复')
        return self
class HistoryRestore(RevisionIn):
    resolve_place_aliases:bool=False
    scope:Literal['content','full']='content'
    confirmation:Literal['恢复为新草稿']
class RecoverySettings(StrictModel):
    retention_days:Literal[7,30,90,'never']=30
    cleanup_confirmed:bool=False
    backup_enabled:bool=True
    frequency:Literal['daily','weekly']='daily'
    weekday:int=Field(default=0,ge=0,le=6)
    hour:int=Field(default=2,ge=0,le=23)
    minute:int=Field(default=0,ge=0,le=59)
    timezone:Literal['Asia/Shanghai','UTC','Asia/Tokyo','America/New_York','Europe/London']='Asia/Shanghai'
    keep:int=Field(default=7,ge=1,le=52)
class SettingsEdit(RecoverySettings):
    cleanup_reviewed:bool=False
    expected_revision:int=Field(ge=0)
class QueueIn(StrictModel):
    expected_settings_revision:int|None=Field(default=None,ge=0)
    kind:Literal['backup','verify','cleanup']
    artifact_id:UUID|None=None
    confirmation:Literal['执行备份','验证备份','永久清理']
    @model_validator(mode='after')
    def valid(self):
        if self.confirmation!={'backup':'执行备份','verify':'验证备份','cleanup':'永久清理'}[self.kind]:raise ValueError('请确认操作')
        if (self.kind=='verify')!=(self.artifact_id is not None):raise ValueError('备份标识不匹配')
        return self
