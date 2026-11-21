"""One lightweight maintenance process, safe to run with duplicate containers.
A PostgreSQL session leader lock serializes scheduling, cleanup, and backup jobs.
No socket mounts, Redis, or web page activity is required.
"""
import os,time,uuid,re
from datetime import datetime,timedelta,timezone
from pathlib import Path
from sqlalchemy import select,text
from .db import engine,SessionLocal
from .migrations import require_current_schema
from .recovery_models import MaintenanceJob,BackupArtifact
from .services.maintenance import settings_data,set_status,next_backup,enqueue
from .services.recovery import db_now,cleanup_batch
from .services.write_barrier import writer
from .backup import readable_target,configured,supervised,verify,backup_root,sha,artifact_path,BackupError,backup_lock,safe_error
LEADER=721934008

def catalog(db,m,verified=True):
    row=db.get(BackupArtifact,m['id'])
    root=backup_root();digest=sha(artifact_path(root,m['id'])/'manifest.json')
    if row:
        if row.manifest_sha256!=digest:raise BackupError('备份清单与登记摘要不一致')
        if verified:row.verified_at=db_now(db)
    else:
        row=BackupArtifact(id=m['id'],created_at=datetime.fromisoformat(m['created_at']),size=sum(f['size'] for f in m['files'].values()),file_count=len(m['files']),manifest_sha256=digest,app_version=m['app_version'],schema_version=m['schema_version'],verified_at=db_now(db) if verified else None);db.add(row)
    return row

def discover(db):
    """Rebuild a lost NVMe catalog from complete backup manifests, without pretending that
    discovery is a checksum/restore test. Only UUID backup directories are read.
    """
    import json,re
    if not readable_target():return
    # Without a root lock, input is a copied, read-only standalone backup.
    from contextlib import nullcontext
    guard=backup_lock() if (backup_root()/'.operation.lock').is_file() else nullcontext()
    with guard,writer(engine):
        for path in backup_root().iterdir():
            try:
                if str(uuid.UUID(path.name))!=path.name or path.is_symlink() or not path.is_dir():continue
                if db.get(BackupArtifact,path.name):continue
                manifest=path/'manifest.json'
                if manifest.is_symlink() or manifest.stat().st_size>20*1024*1024:continue
                m=json.loads(manifest.read_text())
                if m.get('id')!=path.name or m.get('format')!=1 or m.get('complete') is not True:continue
                if not re.fullmatch(r'[A-Za-z0-9._-]{1,100}',m['app_version']) or not isinstance(m['schema_version'],str) or len(m['schema_version'])>40:continue
                if any(type(x['size']) is not int or x['size']<0 for x in m['files'].values()):continue
                with db.begin_nested():catalog(db,m,verified=False)
            except (ValueError,KeyError,TypeError,OSError,BackupError):continue
        db.commit()  # Keep filesystem and PG barriers until discovery is durable.

def retain(db,keep):
    # Global filesystem lock BEFORE any database writer lock, just like create,
    # verify, restore and discovery. Never invoke while holding writer().
    try:
        with backup_lock(exclusive=True),writer(engine):return _retain(db,keep)
    except (BackupError,OSError):
        db.rollback()
        return {'state':'deferred','note':'备份目录忙或不可用，保留全部未清理副本，稍后重试'}

def _retain(db,keep):
    rows=list(db.scalars(select(BackupArtifact).order_by(BackupArtifact.created_at.desc(),BackupArtifact.id)))
    # Only complete, registered, checksum-valid copies count towards retention.
    # One damaged/missing catalog entry conservatively suspends all eviction.
    valid=[]
    for row in rows:
        try:
            verify(row.id)
            if sha(artifact_path(backup_root(),row.id)/'manifest.json')!=row.manifest_sha256:
                raise BackupError('备份清单与登记摘要不一致')
            valid.append(row)
        except (BackupError,OSError):
            return {'state':'deferred','note':'发现缺失或校验失败的副本，暂停淘汰；请核对存储后重试'}
    restored=max((r for r in valid if r.restored_at),key=lambda r:r.restored_at,default=None)
    if not restored:return {'state':'deferred','note':'首次实际恢复演练前不淘汰旧备份'}
    preserved={r.id for r in valid[:keep]}|{restored.id}
    removed=0
    for row in valid:
        if row.id in preserved:continue
        try:
            import shutil,fcntl
            with (artifact_path(backup_root(),row.id)/'manifest.json').open('rb') as lock:
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:
                    return {'state':'deferred','removed':removed,'note':'副本正被独立恢复或校验，停止淘汰并稍后重试'}
                shutil.rmtree(artifact_path(backup_root(),row.id));db.delete(row)
                # Commit each eligible deletion. A later failure never rolls back
                # the catalog for already deleted copies or touches protected ones.
                db.commit();removed+=1
        except (BackupError,OSError):
            db.rollback()
            return {'state':'partial','removed':removed,'note':'旧副本清理中断，停止淘汰；其余完整副本保留，请人工核对'}
    return {'state':'succeeded','removed':removed}

def run_job(id):
    with writer(engine),SessionLocal() as db:
        job=db.scalar(select(MaintenanceJob).where(MaintenanceJob.id==id).with_for_update())
        if job is None or job.state!='queued':return
        job.state='running';job.started_at=db_now(db);kind=job.kind;artifact=job.artifact_id;expected=job.result.get('settings_revision');db.commit()
    result={}
    try:
        if kind=='cleanup':
            with writer(engine),SessionLocal() as db:
                config=settings_data(db)
                result={'removed':0,'errors':[],'examined':0};cursor=None
                def audit(batch):
                    result['removed']+=batch['removed'];result['errors']+=batch['errors'];result['examined']+=batch.get('examined',0)
                    db.get(MaintenanceJob,id).result={**result,'settings_revision':expected}
                for _ in range(200):
                    from .services.archive import write_lock
                    write_lock(db)
                    if not settings_data(db)['cleanup_confirmed']:raise BackupError('管理员尚未确认清理策略，清理暂停')
                    if settings_data(db)['revision']!=expected:raise BackupError('维护策略已改变，停止剩余清理')
                    batch=cleanup_batch(db,config['retention_days'],after=cursor,on_batch=audit)
                    if batch.get('examined',0)<50:break
                    cursor=batch['cursor']
        elif kind=='backup':
            with writer(engine),SessionLocal() as db:
                config=settings_data(db)
                if config['revision']!=expected:raise BackupError('维护策略已改变，请重新确认')
            m=supervised('create')
            with backup_lock(id=m['id']),writer(engine),SessionLocal() as db:catalog(db,m);db.commit()
            with SessionLocal() as db:retention=retain(db,config['keep'])
            result={'backup_id':m['id'],'file_integrity':'passed','restore_validation':'not_run','retention':retention}
        else:
            with backup_lock(id=artifact):
                m=verify(artifact)
                with writer(engine),SessionLocal() as db:catalog(db,m);db.commit()
            result={'backup_id':m['id'],'file_integrity':'passed','restore_validation':'not_run'}
        state='partial' if result.get('errors') or result.get('retention',{}).get('state')=='partial' else 'succeeded';error=''
    except Exception as exc:
        # No paths, SQL error strings, credentials or record values in logs/status.
        state='partial' if result.get('removed',0) else 'failed';error=safe_error(exc)
    with writer(engine),SessionLocal() as db:
        job=db.get(MaintenanceJob,id);job.state=state;job.result=result;job.error=error;job.finished_at=db_now(db);db.commit()

def leader_loop(once=False):
    if engine.dialect.name!='postgresql':raise RuntimeError('维护服务仅支持 PostgreSQL')
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as leader:
        if not leader.scalar(text(f'SELECT pg_try_advisory_lock({LEADER})')):return
        try:
            with writer(engine),SessionLocal() as db:
                for j in db.scalars(select(MaintenanceJob).where(MaintenanceJob.state=='running')):
                    j.state='partial' if j.result.get('removed',0) else 'failed';j.error='执行容器中断；任务未标记成功，可安全重试';j.finished_at=db_now(db)
                db.commit()
            with SessionLocal() as db:discover(db)
            with writer(engine),SessionLocal() as db:
                from .blog_models import SiteConfig
                stored=db.scalar(select(SiteConfig).where(SiteConfig.key=='maintenance_status'))
                state=stored.value if stored else {}
            scheduled=datetime.fromisoformat(state['next_backup']) if state.get('next_backup') else None
            config_revision=state.get('config_revision')
            while True:
                # A broken leader connection must stop work instead of losing exclusivity.
                leader.scalar(text('SELECT 1'))
                with writer(engine),SessionLocal() as db:
                    now=db_now(db);config=settings_data(db)
                    if config_revision!=config['revision'] or scheduled is None:
                        from .services.maintenance import schedule_anchor
                        scheduled=next_backup(config,schedule_anchor(db,config['revision'],now));config_revision=config['revision']
                    if config['cleanup_confirmed']:
                        key='cleanup:'+now.date().isoformat()
                        if not db.scalar(select(MaintenanceJob.id).where(MaintenanceJob.dedupe_key==key)):enqueue(db,'cleanup',dedupe=key)
                    ready=configured()
                    if config['backup_enabled'] and now>=scheduled:
                        key='backup:'+scheduled.isoformat()
                        if not db.scalar(select(MaintenanceJob.id).where(MaintenanceJob.dedupe_key==key)):enqueue(db,'backup',dedupe=key)
                        scheduled=next_backup(config,now)
                    set_status(db,{'heartbeat':now.isoformat(),'configured':ready,'readable_backup':readable_target(),'artifacts_present':[p.name for p in backup_root().iterdir() if re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',p.name) and not p.is_symlink() and p.is_dir()] if readable_target() else [],'config_revision':config_revision,'next_backup':scheduled.isoformat() if config['backup_enabled'] else None,'retention_note':'按设置保留最近完整备份，并保护最后一次实际恢复验证副本；首次演练前暂停旧备份淘汰'})
                    db.commit()
                    job=db.scalar(select(MaintenanceJob).where(MaintenanceJob.state=='queued').order_by(MaintenanceJob.created_at,MaintenanceJob.id).limit(1));id=job.id if job else None
                from .calendar.scheduler import tick
                tick(SessionLocal)
                if id:run_job(id)
                if once:return
                time.sleep(10)
        finally:leader.scalar(text(f'SELECT pg_advisory_unlock({LEADER})'))

def main():
    if os.getenv('AUTO_MIGRATE_ON_STARTUP','false') == 'true':
        from .auto_migrate import startup
        startup(engine)
    else:
        from .migrations import initialize_empty_database
        try: initialize_empty_database(engine)
        except Exception: raise SystemExit('手动迁移模式：数据库未就绪，请运行兼容维护镜像的 python -m app.migrate upgrade；未自动升级旧库') from None
    # Manual mode retains the existing explicit-upgrade workflow.
    for attempt in range(60):
        try:require_current_schema(engine);break
        except Exception:
            if attempt==59:raise SystemExit('数据库结构未就绪，请检查 API 初始化或显式升级')
            time.sleep(2)
    from .backup import prepare_local_target
    try:prepare_local_target()
    except Exception:print('SSD 备份目录未就绪，备份不会标记成功',flush=True)
    if engine.dialect.name!='postgresql':raise SystemExit('维护服务仅支持 PostgreSQL')
    while True:
        try:leader_loop(once=os.getenv('MAINTENANCE_ONCE')=='true')
        except Exception:print('维护周期失败，未输出数据库或私人数据；稍后重试',flush=True)
        if os.getenv('MAINTENANCE_ONCE')=='true':return
        time.sleep(10)
if __name__=='__main__':main()
