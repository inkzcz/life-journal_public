"""One-time bootstrap. Env key is supplied by the owner through NAS Docker GUI.
Never put key into URL, log, DB, cookie or frontend bundle. All writes retain CSRF.
"""
import os,secrets,uuid
from typing import Literal
from ..recovery_schemas import RecoverySettings
from fastapi import APIRouter,Depends,HTTPException,Header
from pydantic import Field,field_validator
from sqlalchemy import select,text
from ..archive_schemas import StrictModel
from ..blog_schemas import Appearance
from ..blog_models import SiteConfig
from ..dependencies import db_dep,get_settings,require_admin
from ..models import User,AdminUser
from ..security import ph,allow_login
from ..passwords import validate_password
from ..services.blog import DEFAULT_LAYOUT

router=APIRouter()

class SetupBackup(StrictModel):
    frequency:Literal['daily','weekly']='daily'
    weekday:int=Field(default=0,ge=0,le=6)
    hour:int=Field(default=2,ge=0,le=23)
    minute:int=Field(default=0,ge=0,le=59)
    timezone:Literal['Asia/Shanghai','UTC','Asia/Tokyo','America/New_York','Europe/London']='Asia/Shanghai'
    keep:int=Field(default=7,ge=1,le=52)

class SetupIn(StrictModel):
    username:str=Field(min_length=1,max_length=100)
    password:str=Field(min_length=8,max_length=1024)
    title:str=Field(min_length=1,max_length=100)
    subtitle:str=Field(default='',max_length=200)
    description:str=Field(default='',max_length=2000)
    appearance:Appearance=Field(default_factory=lambda:Appearance(theme='celadon',style='modern-soft',palette='celadon'))
    home_layout:Literal['feature','grid2','list']='grid2'
    backup:SetupBackup=Field(default_factory=SetupBackup)
    @field_validator('username','title')
    @classmethod
    def nonempty(cls,v):
        if not v.strip():raise ValueError('不能为空')
        return v.strip()
    @field_validator('password')
    @classmethod
    def password_policy(cls,v):return validate_password(v)

def completed(db):
    return db.scalar(select(AdminUser.user_id).limit(1)) is not None or db.scalar(select(SiteConfig.id).where(SiteConfig.key=='setup')) is not None

@router.get('/api/setup/status')
def status(db=Depends(db_dep)):
    # Unauthenticated endpoint intentionally exposes ONLY the bootstrap gate.
    return {'required':not completed(db)}

def authorize(authorization):
    scheme,_,supplied=(authorization or '').partition(' ')
    key=supplied if scheme.lower()=='bearer' else ''
    expected=os.getenv('SETUP_KEY','')
    if not allow_login():raise HTTPException(429,'初始化尝试过多，请稍后重试')
    if len(expected)<32:raise HTTPException(503,'请在容器设置中配置至少32字符的初始化授权密钥')
    if not key or not secrets.compare_digest(key.encode(),expected.encode()):
        raise HTTPException(403,'初始化授权失败')

@router.post('/api/setup/check')
def check(key:str|None=Header(None,alias='Authorization'),db=Depends(db_dep),settings=Depends(get_settings)):
    authorize(key)
    if completed(db):raise HTTPException(409,'初始化已关闭')
    return system_data(db,settings)

@router.post('/api/setup/complete')
def complete(data:SetupIn,key:str|None=Header(None,alias='Authorization'),db=Depends(db_dep)):
    authorize(key)
    # Same transaction serializes all bootstrap requests; crash rolls back ALL seeds.
    if db.bind.dialect.name=='postgresql':
        db.execute(text("SET LOCAL lock_timeout='10s'"))
        db.execute(text('SELECT pg_advisory_xact_lock(721934012)'))
    if completed(db) or db.scalar(select(User.id).limit(1)) is not None:
        raise HTTPException(409,'已有账号或已完成初始化，请使用原账号登录；禁止覆盖')
    user=User(username=data.username,password_hash=ph.hash(data.password));db.add(user);db.flush()
    db.add(AdminUser(user_id=user.id))
    def seed(key,value):
        if db.scalar(select(SiteConfig.id).where(SiteConfig.key==key)) is None:
            db.add(SiteConfig(id=str(uuid.uuid4()),key=key,value=value,revision=1))
    import copy
    layout=copy.deepcopy(DEFAULT_LAYOUT)
    layout.update(title=data.title,description=data.description)
    layout['modules'][1]['layout']=data.home_layout
    seed('layout',layout)
    seed('recovery',RecoverySettings(**data.backup.model_dump()).model_dump())
    from ..services.maintenance import mark_schedule_changed,settings_data
    mark_schedule_changed(db,settings_data(db)['revision'])
    seed('appearance',data.appearance.model_dump())
    seed('site_text',{'site.subtitle':data.subtitle} if data.subtitle else {})
    from ..template_presets import presets
    from ..template_schemas import TemplateIn
    from ..services.templates import save_template
    from ..template_models import ContentTemplate
    for preset in presets():
        slug='initial-'+preset.pop('key')
        if db.scalar(select(ContentTemplate.id).where(ContentTemplate.slug==slug)) is None:
            save_template(db,TemplateIn(**{**preset,'slug':slug}),user.id)
    seed('setup',{'complete':True})
    db.commit()
    return {'ok':True}

def system_data(db,settings):
    from ..migrations import HEAD,require_current_schema
    from ..services.maintenance import status_data
    from ..recovery_models import BackupArtifact,MaintenanceJob
    from ..backup import version,BackupError
    require_current_schema(db.bind)
    writable=False
    try:
        from tempfile import TemporaryFile
        from ..services.write_barrier import writer
        # Even a GET status probe must respect the filesystem backup barrier.
        # TemporaryFile never removes a pre-existing path and normally uses an
        # anonymous inode; do not insert a health file into a frozen media copy.
        with writer(db.bind):
            settings.media_dir.mkdir(parents=True,exist_ok=True)
            with TemporaryFile(dir=settings.media_dir,prefix='.health-') as probe:
                probe.write(b'probe');probe.flush()
            writable=True
    except HTTPException as exc:
        if exc.status_code!=503:raise
        writable=None  # Busy is not the same as an unwritable directory.
    except OSError:pass
    try:app_version=version()
    except BackupError:app_version='unversioned'
    latest=db.scalar(select(BackupArtifact).order_by(BackupArtifact.created_at.desc()).limit(1))
    restored=db.scalar(select(BackupArtifact).where(BackupArtifact.restored_at.is_not(None)).order_by(BackupArtifact.restored_at.desc()).limit(1))
    job=db.scalar(select(MaintenanceJob).where(MaintenanceJob.kind=='backup').order_by(MaintenanceJob.created_at.desc()).limit(1))
    from ..version import __version__
    return {'release_version':__version__,'latest_restore_validation':{'id':restored.id,'restored_at':restored.restored_at.isoformat()} if restored else None,'latest_backup_task':{'state':job.state,'error':job.error} if job else None,'application_version':app_version,'postgresql':'ok','schema':HEAD,'api':'ok',
            'media_writable':writable,'maintenance':status_data(db),
            'latest_backup':{'id':latest.id,'verified_at':latest.verified_at.isoformat() if latest.verified_at else None,'restored_at':latest.restored_at.isoformat() if latest.restored_at else None} if latest else None}

@router.get('/api/admin/system',dependencies=[Depends(require_admin)])
def system(db=Depends(db_dep),settings=Depends(get_settings)):return system_data(db,settings)
