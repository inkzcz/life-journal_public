import uuid
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from ..dependencies import db_dep,require_admin,get_settings
from ..recovery_schemas import SettingsEdit,QueueIn
from ..recovery_models import MaintenanceJob,BackupArtifact
from ..services.maintenance import settings_data,status_data,enqueue,job_data
from ..services.archive import write_lock
from ..services.blog import save_config
router=APIRouter(prefix='/api/admin/maintenance',dependencies=[Depends(require_admin)])

@router.get('/settings')
def settings(db=Depends(db_dep)):return settings_data(db)

@router.put('/settings')
def save_settings(data:SettingsEdit,db=Depends(db_dep)):
    from ..services.maintenance import mark_schedule_changed,mark_cleanup_review
    if data.cleanup_confirmed and not data.cleanup_reviewed:
        raise HTTPException(422,'统一系统升级后请明确重新审核清理策略，再确认保存')
    write_lock(db);save_config(db,'recovery',data.model_dump(exclude={'expected_revision','cleanup_reviewed'}),data.expected_revision)
    mark_schedule_changed(db,data.expected_revision+1)
    mark_cleanup_review(db,data.cleanup_confirmed)
    db.commit();return settings_data(db)

@router.get('/status')
def status(db=Depends(db_dep),app_settings=Depends(get_settings)):
    return {**status_data(db),'dynamic_blog':True}

@router.get('/jobs')
def jobs(db=Depends(db_dep)):
    return [job_data(j) for j in db.scalars(select(MaintenanceJob).order_by(MaintenanceJob.created_at.desc(),MaintenanceJob.id).limit(50))]

@router.get('/backups')
def backups(db=Depends(db_dep)):
    status=status_data(db)
    return [{k:getattr(b,k) for k in ['id','size','file_count','app_version','schema_version']}|{'present':b.id in status.get('artifacts_present',[]) if status['online'] and status.get('heartbeat') and status['heartbeat']>=b.created_at.isoformat() else None}|{k:getattr(b,k).isoformat() if getattr(b,k) else None for k in ['created_at','verified_at','restored_at']} for b in db.scalars(select(BackupArtifact).order_by(BackupArtifact.created_at.desc()).limit(100))]

@router.post('/jobs')
def queue(data:QueueIn,db=Depends(db_dep),actor=Depends(require_admin),app_settings=Depends(get_settings)):
    write_lock(db);status=status_data(db)
    if data.kind=='cleanup' and not settings_data(db)['cleanup_confirmed']:raise HTTPException(409,'管理员尚未确认清理策略，请先保存确认后再执行')
    if not status['online']:raise HTTPException(503,'维护执行容器未运行，请查看部署说明')
    if (data.kind=='backup' and not status['configured'] or data.kind=='verify' and not status.get('readable_backup')):raise HTTPException(409,'SSD 备份目录不可用，未创建备份')
    if data.kind!='verify' and data.expected_settings_revision!=settings_data(db)['revision']:raise HTTPException(409,'维护策略已变更，请重新读取设置后再确认执行')
    if data.artifact_id and not db.get(BackupArtifact,str(data.artifact_id)):raise HTTPException(404,'备份不存在')
    if db.scalar(select(MaintenanceJob.id).where(MaintenanceJob.state.in_(['queued','running']),MaintenanceJob.kind==data.kind).limit(1)):
        raise HTTPException(409,'相同任务正在等待或执行')
    j=enqueue(db,data.kind,actor.id,str(data.artifact_id) if data.artifact_id else None);db.commit();return job_data(j)
