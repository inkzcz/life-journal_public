"""Small persistent scheduler configuration. PostgreSQL UTC is the clock authority."""
import uuid
from datetime import datetime,timedelta,timezone,time
from zoneinfo import ZoneInfo
from sqlalchemy import select
from ..blog_models import SiteConfig
from ..recovery_models import MaintenanceJob
from ..recovery_schemas import RecoverySettings
from .recovery import db_now

def settings_data(db):
    row=db.scalar(select(SiteConfig).where(SiteConfig.key=='recovery'))
    config={**RecoverySettings().model_dump(),**(row.value if row else {}),'revision':row.revision if row else 0}
    if config['cleanup_confirmed']:
        receipt=db.scalar(select(SiteConfig).where(SiteConfig.key=='cleanup_consent'))
        value=receipt.value if receipt and isinstance(receipt.value,dict) else {}
        # Do not silently resume a legacy cleanup that the retired feature flag
        # may have paused. Reading this gate NEVER rewrites the stored strategy.
        config['cleanup_confirmed']=bool(row and row.value.get('cleanup_confirmed') is True and value.get('policy')=='phase4a'
            and value.get('settings_id')==row.id and value.get('revision')==row.revision
            and value.get('confirmed') is True)
    return config

def next_backup(config,after):
    zone=ZoneInfo(config['timezone']);local=after.astimezone(zone)
    for delta in range(15):
        day=local.date()+timedelta(days=delta)
        if config.get('frequency','weekly')=='weekly' and day.weekday()!=config['weekday']:continue
        candidate=datetime.combine(day,time(config['hour'],config['minute']),zone).replace(fold=0)
        utc=candidate.astimezone(timezone.utc)
        # Skip non-existent DST wall times. Ambiguous times run only at fold=0.
        if utc.astimezone(zone).replace(tzinfo=None)!=candidate.replace(tzinfo=None):continue
        if utc>after:return utc
    raise ValueError('无法计算下一次执行时间')

def status_data(db):
    row=db.scalar(select(SiteConfig).where(SiteConfig.key=='maintenance_status'))
    value=row.value if row else {}
    now=db_now(db);heartbeat=value.get('heartbeat')
    online=bool(heartbeat and now-datetime.fromisoformat(heartbeat)<timedelta(seconds=120))
    config=settings_data(db)
    return {**value,'online':online,'configured':online and value.get('configured',False),
            'now':now.isoformat(),'next_backup':value.get('next_backup') if config['backup_enabled'] and online else None}

def set_status(db,value):
    row=db.scalar(select(SiteConfig).where(SiteConfig.key=='maintenance_status'))
    if row:row.value=value;row.revision+=1
    else:db.add(SiteConfig(id=str(uuid.uuid4()),key='maintenance_status',value=value,revision=1))

def enqueue(db,kind,actor=None,artifact_id=None,dedupe=None):
    job=MaintenanceJob(id=str(uuid.uuid4()),kind=kind,requested_by=actor,artifact_id=artifact_id,dedupe_key=dedupe,created_at=db_now(db),state='queued',result={'settings_revision':settings_data(db)['revision']},error='')
    db.add(job);db.flush();return job

def job_data(j):return {k:getattr(j,k) for k in ['id','kind','state','result','error']}|{k:getattr(j,k).isoformat() if getattr(j,k) else None for k in ['created_at','started_at','finished_at']}


def mark_schedule_changed(db,revision):
    """Same transaction as config save, database clock; never a client timestamp."""
    value={'config_revision':revision,'changed_at':db_now(db).isoformat()}
    row=db.scalar(select(SiteConfig).where(SiteConfig.key=='schedule_clock'))
    if row:row.value=value;row.revision+=1
    else:db.add(SiteConfig(id=str(uuid.uuid4()),key='schedule_clock',value=value,revision=1))
    db.flush()


def schedule_anchor(db,revision,now):
    row=db.scalar(select(SiteConfig).where(SiteConfig.key=='schedule_clock'))
    if row and row.value.get('config_revision')==revision:
        try:
            value=datetime.fromisoformat(row.value['changed_at'])
            if value.tzinfo is not None:return min(value,now)
        except (ValueError,KeyError,TypeError):pass
    # Old installations have no anchor: no retroactive catch-up is inferred.
    return now


def mark_cleanup_review(db,confirmed):
    strategy=db.scalar(select(SiteConfig).where(SiteConfig.key=='recovery'))
    if strategy is None:raise ValueError('清理策略尚未保存')
    value={'policy':'phase4a','settings_id':strategy.id,'revision':strategy.revision,
           'confirmed':bool(confirmed),'reviewed_at':db_now(db).isoformat()}
    row=db.scalar(select(SiteConfig).where(SiteConfig.key=='cleanup_consent'))
    if row:row.value=value;row.revision+=1
    else:db.add(SiteConfig(id=str(uuid.uuid4()),key='cleanup_consent',value=value,revision=1))
    db.flush()
