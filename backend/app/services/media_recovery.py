"""Explicit recoverable deletion. Database rollback never pretends to undo unlink."""
import os,uuid,hashlib
from contextlib import contextmanager
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select,text
from ..archive_models import MediaAsset,MediaPurgeOperation
from ..models import now
from .archive import write_lock
from .uploads import _local_lock
from .write_barrier import writer
from .resource_usage import assert_media_unused,require_audit
NAMES={'original','preview.webp','thumbnail.webp'}

def checkpoint(stage):pass  # Process-failure tests patch this function, never an environment flag.

def safe(path):
    if any(p.is_symlink() for p in [path,*path.parents]):raise HTTPException(409,'拒绝符号链接，文件未删除')
    return path

def inventory(path,manifest,partial=False):
    safe(path)
    if not path.exists():
        if partial:return
        raise HTTPException(409,'资源文件缺失，停止删除，请核对完整备份')
    if not path.is_dir() or set(p.name for p in path.iterdir())-set(manifest):raise HTTPException(409,'发现非预期文件，停止删除')
    for name,digest in manifest.items():
        if name not in NAMES or len(digest)!=64:raise HTTPException(409,'文件日志无效')
        p=safe(path/name)
        if not p.exists() and partial:continue
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise HTTPException(409,'资源完整性不一致，停止删除')

def fsync_dir(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

@contextmanager
def operation_lock(db):
    with writer(db.bind):
        if db.bind.dialect.name!='postgresql':
            if not _local_lock.acquire(timeout=5):raise HTTPException(409,'文件操作忙，请稍后重试')
            try:yield
            finally:_local_lock.release()
        else:
            with db.bind.connect().execution_options(isolation_level='AUTOCOMMIT') as con:
                if not con.scalar(text('SELECT pg_try_advisory_lock(721934014)')):raise HTTPException(409,'其他媒体删除正在进行，请重试原操作')
                try:yield
                finally:con.scalar(text('SELECT pg_advisory_unlock(721934014)'))

def paths(root,op):
    root=safe(Path(root));parent=safe(root/'.purge-v1'/op.id)
    return safe(root/'library-v1'/op.media_id),parent,safe(parent/op.media_id)

def operation_data(op):
    return {k:getattr(op,k) for k in ['id','media_id','state','error_code']}|{'created_at':op.created_at.isoformat()}

def _advance(db,op,root):
    source,parent,isolated=paths(root,op)
    if op.state in ('completed','cancelled'):return operation_data(op)
    if op.state in ('prepared','isolated'):
        write_lock(db);m=db.get(MediaAsset,op.media_id)
        if m is None or m.purge_operation_id!=op.id or m.deleted_at is None:raise HTTPException(409,'删除状态不一致，文件保留')
        require_audit(db);assert_media_unused(db,m.id)
        if source.exists() and isolated.exists():raise HTTPException(409,'原目录与隔离目录同时存在，停止操作')
        if source.exists():
            inventory(source,op.manifest)
            safe(parent.parent).mkdir(mode=0o700,exist_ok=True);parent.mkdir(mode=0o700,exist_ok=True)
            os.rename(source,isolated);fsync_dir(source.parent);fsync_dir(parent);fsync_dir(parent.parent)
            checkpoint('after_rename')
        else:inventory(isolated,op.manifest)
        op.state='isolated';op.error_code='';op.updated_at=now();db.commit();checkpoint('isolated')
        write_lock(db);m=db.get(MediaAsset,op.media_id)
        if m is None or m.purge_operation_id!=op.id:raise HTTPException(409,'删除状态已改变')
        require_audit(db);assert_media_unused(db,m.id);inventory(isolated,op.manifest)
        db.delete(m);op.state='db_committed';op.updated_at=now();db.commit();checkpoint('db_committed')
    if op.state=='db_committed':
        if source.exists():raise HTTPException(409,'数据库已提交但原目录仍存在，请核对日志')
        inventory(isolated,op.manifest,partial=True)
        if isolated.exists():
            for name in op.manifest:
                p=safe(isolated/name)
                if p.exists():p.unlink();fsync_dir(isolated);checkpoint('after_unlink')
            isolated.rmdir();fsync_dir(parent)
        if parent.exists():parent.rmdir();fsync_dir(parent.parent)
        checkpoint('files_removed')
        write_lock(db);op.state='completed';op.error_code='';op.updated_at=now();db.commit()
    return operation_data(op)

def purge_media(db,id,revision,actor,key,root):
    with operation_lock(db):
        write_lock(db)
        op=db.scalar(select(MediaPurgeOperation).where(MediaPurgeOperation.actor_id==actor,MediaPurgeOperation.request_key==key))
        if op and op.media_id!=id:raise HTTPException(409,'请求标识已用于其他图片')
        if not op:
            require_audit(db);m=db.get(MediaAsset,id)
            if m is None:raise HTTPException(404,'图片不存在')
            if m.deleted_at is None:raise HTTPException(409,'请先移入回收站')
            if m.purge_operation_id:raise HTTPException(409,'图片已有待处理删除，请在操作日志中继续或取消')
            if m.revision!=revision:raise HTTPException(409,'图片版本已更新')
            assert_media_unused(db,id)
            manifest={'original':m.sha256,'preview.webp':m.preview_sha256}
            if m.thumbnail_sha256:manifest['thumbnail.webp']=m.thumbnail_sha256
            op=MediaPurgeOperation(id=str(uuid.uuid4()),media_id=id,actor_id=actor,request_key=key,state='prepared',manifest=manifest)
            inventory(safe(Path(root)/'library-v1'/id),manifest)
            db.add(op);db.flush();m.purge_operation_id=op.id;m.revision+=1;db.commit();checkpoint('prepared')
        return _advance(db,op,root)

def resume(db,id,root,cancel=False):
    with operation_lock(db):
        write_lock(db);op=db.get(MediaPurgeOperation,id)
        if not op:raise HTTPException(404,'操作不存在')
        if not cancel:return _advance(db,op,root)
        if op.state=='cancelled':return operation_data(op)
        if op.state not in ('prepared','isolated'):raise HTTPException(409,'数据库删除已提交，不能取消；只能重试文件清理或使用备份恢复')
        source,parent,isolated=paths(root,op);m=db.get(MediaAsset,op.media_id)
        if not m or m.purge_operation_id!=op.id:raise HTTPException(409,'日志与资源不一致，停止操作')
        if source.exists() and isolated.exists():raise HTTPException(409,'存在重复目录，停止操作')
        if isolated.exists():
            inventory(isolated,op.manifest);os.rename(isolated,source);fsync_dir(source.parent);fsync_dir(parent)
        else:inventory(source,op.manifest)
        if parent.exists():parent.rmdir();fsync_dir(parent.parent)
        m.purge_operation_id=None;m.revision+=1;op.state='cancelled';op.updated_at=now();db.commit()
        return operation_data(op)

def restore_media(db,id,revision,root):
    write_lock(db);m=db.get(MediaAsset,id)
    if not m:raise HTTPException(404,'图片不存在')
    if m.purge_operation_id:raise HTTPException(409,'图片存在未完成删除，请先明确取消操作')
    if m.deleted_at is None:return {'id':id,'state':'already_active'}
    if m.revision!=revision:raise HTTPException(409,'图片已更新')
    manifest={'original':m.sha256,'preview.webp':m.preview_sha256}
    if m.thumbnail_sha256:manifest['thumbnail.webp']=m.thumbnail_sha256
    inventory(safe(Path(root)/'library-v1'/id),manifest)
    m.deleted_at=None;m.revision+=1;db.commit();return {'id':id,'state':'restored'}

def validate_backup_media(db,root,*,assets=None):
    """Read only under the backup's existing exclusive writer barrier."""
    operations=list(db.scalars(select(MediaPurgeOperation)))
    known={o.id:o for o in operations};quarantine=safe(Path(root)/'.purge-v1')
    if quarantine.exists():
        for p in quarantine.iterdir():
            if p.name not in known:raise RuntimeError('存在未知媒体隔离目录，备份已停止')
    for op in operations:
        source,parent,isolated=paths(root,op)
        if parent.exists() and set(p.name for p in parent.iterdir())-{op.media_id}:raise RuntimeError('隔离目录含未知文件')
        if op.state in ('prepared','isolated'):
            if source.exists()==isolated.exists():raise RuntimeError('未完成媒体日志与文件不一致')
            inventory(source if source.exists() else isolated,op.manifest)
        elif op.state=='db_committed':
            if source.exists():raise RuntimeError('已提交媒体删除仍有原目录')
            inventory(isolated,op.manifest,partial=True)
        elif parent.exists():raise RuntimeError('已结束操作仍有隔离文件')

    from ..archive_models import MediaUploadOperation
    uploads=list(db.scalars(select(MediaUploadOperation)))
    upload_map={u.id:u for u in uploads};staging=safe(Path(root)/'.staging-v1')
    if staging.exists():
        for directory in staging.iterdir():
            safe(directory)
            if directory.name not in upload_map or not directory.is_dir() or set(p.name for p in directory.iterdir())-NAMES:raise RuntimeError('未知上传临时目录，备份已停止')
            for p in directory.iterdir():
                safe(p)
                if not p.is_file():raise RuntimeError('上传临时目录含特殊文件')
    assets=list(db.scalars(select(MediaAsset))) if assets is None else assets
    allowed={m.id for m in assets}|{u.media_id for u in uploads if u.state=='pending'}|{o.media_id for o in operations if o.state in ('prepared','isolated')}
    from ..exchange.backup import inventory as exchange_inventory
    allowed |= exchange_inventory(db,root)
    library=safe(Path(root)/'library-v1')
    if library.exists():
        for p in library.iterdir():
            safe(p)
            if p.name not in allowed or not p.is_dir():raise RuntimeError('存在未知媒体目录，备份已停止')
    for m in assets:
        if m.purge_operation_id:
            op=known.get(m.purge_operation_id)
            if not op or op.media_id!=m.id or op.state not in ('prepared','isolated') or m.deleted_at is None:raise RuntimeError('媒体删除标记与日志不一致')
            continue
        manifest={'original':m.sha256,'preview.webp':m.preview_sha256}
        if m.thumbnail_sha256:manifest['thumbnail.webp']=m.thumbnail_sha256
        inventory(safe(Path(root)/'library-v1'/m.id),manifest)
    for u in uploads:
        if u.state!='pending':continue
        target=safe(Path(root)/'library-v1'/u.media_id)
        if target.exists():
            if not (target/'original').is_file() or hashlib.sha256((target/'original').read_bytes()).hexdigest()!=u.sha256 or set(p.name for p in target.iterdir())!=NAMES:raise RuntimeError('待提交上传的完整性不一致')
