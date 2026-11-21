"""Idempotent, replayable private uploads under the existing backup writer barrier.
A killed process leaves a pending journal and controlled staging files. Retrying the
same key/file resumes; nothing is automatically deleted or promoted on startup.
"""
import hashlib
import os
import uuid
import threading
import shutil
from contextlib import contextmanager
from sqlalchemy import select,text
from fastapi import HTTPException
from ..archive_models import MediaAsset,MediaUploadOperation
from ..models import now
from .archive import asset_data,write_lock

_local_lock=threading.Lock()

@contextmanager
def upload_lock(db):
    if db.bind.dialect.name!='postgresql':
        if not _local_lock.acquire(timeout=5):raise HTTPException(409,'其他上传正在完成，请稍后使用相同上传项重试')
        try:yield
        finally:_local_lock.release()
        return
    # Dedicated fixed connection; session lock survives commits and process death releases it.
    with db.bind.connect() as con:
        acquired=con.scalar(text('SELECT pg_try_advisory_lock(721934013)'))
        if not acquired:raise HTTPException(409,'其他上传正在完成，请稍后使用相同上传项重试')
        try:yield
        finally:con.execute(text('SELECT pg_advisory_unlock(721934013)'))


def directory(root,*parts):
    if root.is_symlink():raise HTTPException(409,'媒体目录不能是符号链接')
    path=root
    for part in parts:
        path=path/part
        if path.is_symlink():raise HTTPException(409,'媒体目录不能是符号链接')
        path.mkdir(mode=0o700,parents=True,exist_ok=True)
    return path


def save_upload(db,user,settings,key,files,metadata,folder_id=None,auto_archive=True):
    try:key=str(uuid.UUID(key)) if key else str(uuid.uuid4())
    except ValueError:raise HTTPException(422,'上传请求标识无效') from None
    digest=hashlib.sha256(files['original']).hexdigest()
    with upload_lock(db):
        op=db.scalar(select(MediaUploadOperation).where(MediaUploadOperation.uploaded_by==user.id,MediaUploadOperation.request_key==key))
        if op:
            if op.sha256!=digest:raise HTTPException(409,'相同上传请求标识不能用于不同文件')
            if op.state=='completed':
                m=db.get(MediaAsset,op.media_id)
                if m is None or m.deleted_at:raise HTTPException(409,'此前上传的图片已被删除，请在媒体库核对')
                return asset_data(m)
        else:
            op=MediaUploadOperation(id=str(uuid.uuid4()),uploaded_by=user.id,request_key=key,media_id=str(uuid.uuid4()),sha256=digest,state='pending')
            db.add(op);db.commit()
        root=settings.media_dir
        staging=directory(root,'.staging-v1',op.id)
        library=directory(root,'library-v1')
        target=library/op.media_id
        if target.is_symlink():raise HTTPException(409,'媒体目录状态异常，请核对上传日志')
        if target.exists():
            for name,data in files.items():
                p=target/name
                if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).digest()!=hashlib.sha256(data).digest():
                    raise HTTPException(409,'已存在的上传目录完整性异常，原文件已保留')
        else:
            for name,data in files.items():
                p=staging/name
                if p.is_symlink():raise HTTPException(409,'临时上传文件状态异常')
                # A retry may replace only its own known temporary files.
                with p.open('wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
            fd=os.open(staging,os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
            os.rename(staging,target)
            for folder in (library,root/'.staging-v1'):
                fd=os.open(folder,os.O_RDONLY)
                try:os.fsync(fd)
                finally:os.close(fd)
        write_lock(db)
        from .folders import require_folder
        require_folder(db,folder_id)
        m=MediaAsset(id=op.media_id,created_at=now(),uploaded_by=user.id,folder_id=str(folder_id) if folder_id else None,**metadata)
        id=op.media_id
        db.add(m);op.state='completed'
        try:
            from .organization import auto_upload
            if auto_archive:
                with db.no_autoflush:auto_upload(db,m)
            db.commit()
        except Exception:
            db.rollback()
            # A lost response after commit must never delete a committed asset.
            confirmed=db.get(MediaAsset,id)
            if confirmed is not None:return asset_data(confirmed)
            # Ordinary rollback: remove only this operation's verified files.
            # SIGKILL cannot enter this handler; durable pending journal survives.
            if target.is_dir() and not target.is_symlink() and set(p.name for p in target.iterdir())==set(files):
                if all(not (target/name).is_symlink() and hashlib.sha256((target/name).read_bytes()).digest()==hashlib.sha256(data).digest() for name,data in files.items()):shutil.rmtree(target)
            raise
        return asset_data(m)
