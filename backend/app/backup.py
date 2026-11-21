"""Private, versioned PostgreSQL+media backups. No web-supplied filesystem paths.
All destructive restore operations require an explicit CLI and empty targets.
"""
from contextlib import contextmanager
import fcntl
import argparse,hashlib,json,os,re,shutil,signal,subprocess,sys,uuid
from pathlib import Path
from datetime import datetime,timezone
from sqlalchemy import inspect,select,text
from .db import engine,Base
from . import tag_models,models,content_models,archive_models,blog_models,template_models,life_models,recovery_models,v5_models
from .migrations import HEAD,require_current_schema
from .services.write_barrier import frozen
FORMAT=1
MARKER='life-journal-backup-target-v1\n'

class BackupError(RuntimeError):pass

def safe_error(error):
    import errno
    if isinstance(error,BackupError):return str(error)[:200]
    if isinstance(error,PermissionError) or isinstance(error,shutil.Error):return '媒体或备份目录权限不足，请核对维护容器UID及目录所有者'
    if isinstance(error,OSError) and error.errno==errno.ENOSPC:return '存储空间不足，未发布完整备份'
    if isinstance(error,FileNotFoundError):return '所需目录或PostgreSQL工具不存在，请使用兼容的维护镜像'
    if isinstance(error,subprocess.CalledProcessError):return 'PostgreSQL备份或恢复工具失败，请检查连接、版本和空间'
    return '任务失败，未标记成功；请检查维护容器及存储状态'

def version():
    built=Path(__file__).resolve().parents[1]/'BUILD_VERSION'
    value=built.read_text().strip() if built.is_file() else os.getenv('LIFE_JOURNAL_VERSION','unversioned')
    if value=='unversioned' or not re.fullmatch(r'[A-Za-z0-9._-]{1,100}',value):raise BackupError('应用版本未固定，请按备份部署说明配置')
    return value

def no_symlinks(path):
    path=Path(path).absolute()
    if any(p.is_symlink() for p in [path,*path.parents]):raise BackupError('拒绝符号链接路径')
    return path

def backup_root():
    raw=os.getenv('BACKUP_ROOT','')
    if not raw:raise BackupError('SSD 本地备份目录未配置')
    root=no_symlinks(Path(raw));media=no_symlinks(Path(os.environ['MEDIA_DIR']))
    if root==Path('/') or root==media or root in media.parents or media in root.parents:raise BackupError('备份目录必须独立于运行媒体目录')
    return root

def readable_target():
    try:
        version();root=backup_root()
        return root.is_dir() and os.access(root,os.R_OK|os.X_OK)
    except (BackupError,OSError):return False

def configured():
    try:
        root=backup_root()
        return readable_target() and not (root/'.operation.lock').is_symlink() and (root/'.operation.lock').is_file() and os.access(root,os.W_OK)
    except (BackupError,OSError):return False

def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

def files(root):
    result={}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise BackupError('备份不接受符号链接')
        if p.is_dir():continue
        if not p.is_file():raise BackupError('发现非普通文件')
        result[p.relative_to(root).as_posix()]={'size':p.stat().st_size,'sha256':sha(p)}
    return result

def db_fingerprint(con):
    result={}
    # The advisory-lock connection stays in autocommit. A separate read-only
    # transaction allows bounded server-side cursors while writers remain frozen.
    with con.engine.connect() as reader:
        if reader.dialect.name=='postgresql':
            reader.execute(text("SET TRANSACTION READ ONLY"))
            reader.execute(text("SET TIME ZONE 'UTC'"))
        for table in Base.metadata.sorted_tables:
            digest=hashlib.sha256();count=0
            query=select(table).order_by(*table.primary_key.columns)
            for row in reader.execute(query.execution_options(stream_results=True)).yield_per(500):
                digest.update(json.dumps(list(row),sort_keys=True,ensure_ascii=False,default=str,separators=(',',':')).encode());digest.update(b'\n');count+=1
            result[table.name]={'rows':count,'sha256':digest.hexdigest()}
    return result

def pg_env(bind):
    u=bind.url
    return {**os.environ,'PGHOST':u.host or 'db','PGPORT':str(u.port or 5432),'PGUSER':u.username or '',
            'PGPASSWORD':u.password or '','PGDATABASE':u.database or ''}

def pg_major(con):return int(con.scalar(text("SHOW server_version_num")))//10000

def artifact_path(root,id):
    try:canonical=str(uuid.UUID(str(id)))
    except ValueError:raise BackupError('无效备份标识') from None
    if str(id)!=canonical:raise BackupError('无效备份标识')
    p=no_symlinks(root/canonical)
    if not p.is_dir():raise BackupError('备份不存在')
    return p

def verify(id,root=None):
    root=root or backup_root();p=artifact_path(root,id)
    try:
        manifest_path=p/'manifest.json'
        if manifest_path.is_symlink() or manifest_path.stat().st_size>20*1024*1024:raise BackupError('清单不合法')
        m=json.loads(manifest_path.read_text())
        if m.get('format')!=FORMAT or m.get('id')!=str(id) or m.get('complete') is not True:raise BackupError('备份格式或完成标记不匹配')
        actual=files(p);actual.pop('manifest.json',None)
        if actual!=m['files'] or 'database.dump' not in actual or not (p/'media').is_dir():raise BackupError('文件校验失败，备份不可使用')
        if not isinstance(m.get('tables'),dict):raise BackupError('逻辑数据校验信息缺失')
        return m
    except (OSError,KeyError,ValueError,TypeError):raise BackupError('备份清单损坏或文件不可读') from None

@contextmanager
def backup_lock(exclusive=False,id=None):
    path=no_symlinks(backup_root()/'.operation.lock')
    # A single complete UUID directory remains independently restorable, even
    # when copied without the old root marker/lock into read-only backup input.
    if not path.is_file() and id is not None and not exclusive:path=artifact_path(backup_root(),id)/'manifest.json'
    with path.open('rb') as lock:
        try:fcntl.flock(lock,(fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)|fcntl.LOCK_NB)
        except BlockingIOError:raise BackupError('备份目录忙，其他创建、校验、恢复或清理正在运行；未执行本次操作，请稍后重试') from None
        try:yield
        finally:fcntl.flock(lock,fcntl.LOCK_UN)

def create_backup(id=None):
    with backup_lock(exclusive=True):return _create_backup(id)

def _create_backup(id=None):
    if not configured():raise BackupError('独立备份目录、标记或应用版本未配置')
    require_current_schema(engine);root=backup_root();id=str(uuid.UUID(id)) if id else str(uuid.uuid4())
    target=root/id
    if target.exists():raise BackupError('备份标识已存在，拒绝覆盖')
    tmp=root/('.partial-'+id);tmp.mkdir(mode=0o700)
    try:
        with frozen(engine) as con:
            from .services.media_recovery import validate_backup_media
            from sqlalchemy.orm import Session
            with Session(engine) as validation:validate_backup_media(validation,Path(os.environ['MEDIA_DIR']))
            major=pg_major(con)
            if major!=17:raise BackupError('当前备份格式仅验证 PostgreSQL 17')
            subprocess.run(['pg_dump','--format=custom','--no-owner','--no-acl','--file',str(tmp/'database.dump')],env=pg_env(engine),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=600)
            source=no_symlinks(Path(os.environ['MEDIA_DIR']))
            if not source.is_dir():raise BackupError('运行媒体目录不可用')
            # Reject symlinks/special files before copy; source writes are frozen.
            original_files=files(source)
            shutil.copytree(source,tmp/'media',symlinks=False)
            if files(tmp/'media')!=original_files:raise BackupError('媒体复制完整性校验失败')
            logical=db_fingerprint(con)
            revision=con.scalar(text('SELECT version_num FROM alembic_version'))
        # The immutable temp copy can be hashed after releasing the write freeze.
        inventory=files(tmp)
        m={'format':FORMAT,'id':id,'app_version':version(),'schema_version':revision,'postgresql_major':major,
           'created_at':datetime.now(timezone.utc).isoformat(),'complete':True,'files':inventory,'tables':logical,
           'required_external_config':['POSTGRES_USER','POSTGRES_PASSWORD','POSTGRES_DB','COOKIE_SECURE'],
           'consistency':'exclusive application writer barrier across pg_dump and media copy'}
        (tmp/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,sort_keys=True,indent=2))
        # Durably flush files before publishing the directory on the same filesystem.
        for p in tmp.rglob('*'):
            if p.is_file():
                with p.open('rb') as f:os.fsync(f.fileno())
        for directory in sorted([tmp,*[p for p in tmp.rglob('*') if p.is_dir()]],key=lambda p:len(p.parts),reverse=True):
            fd=os.open(directory,os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        check=files(tmp);check.pop('manifest.json',None)
        if check!=inventory:raise BackupError('发布前完整性校验失败')
        os.rename(tmp,target)
        fd=os.open(root,os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        verify(id,root)
        return m
    except BaseException:
        # An interrupted .partial is never considered a successful backup.
        # Keep it for diagnostics; do not remove an existing successful directory.
        raise

def restore(id,confirm_empty=False,report=None):
    with backup_lock(id=id):return _restore(id,confirm_empty,report)

def _restore(id,confirm_empty=False,report=None):
    if not confirm_empty:raise BackupError('必须明确确认仅恢复到全新空目标')
    if report:
        report_path=no_symlinks(Path(report))
        media_path=no_symlinks(Path(os.environ['MEDIA_DIR']))
        if report_path.exists() or not report_path.parent.is_dir() or media_path==report_path or media_path in report_path.parents or backup_root() in report_path.parents:
            raise BackupError('恢复报告必须是独立目录中尚不存在的文件')
    m=verify(id);source=artifact_path(backup_root(),id)
    if m['app_version']!=version() or m['schema_version']!=HEAD or m['postgresql_major']!=17:raise BackupError('应用、迁移或 PostgreSQL 版本不兼容，拒绝恢复')
    media=no_symlinks(Path(os.environ['MEDIA_DIR']))
    if media.exists() and any(media.iterdir()):raise BackupError('目标媒体目录非空，拒绝覆盖')
    with frozen(engine) as con:
        existing=con.scalar(text("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema' AND c.relkind IN ('r','p','v','m','S','f')"))
        schemas=con.scalar(text("SELECT count(*) FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname NOT IN ('public','information_schema')"))
        if existing or schemas:raise BackupError('目标数据库非空，拒绝覆盖')
        if pg_major(con)!=m['postgresql_major']:raise BackupError('PostgreSQL 主版本不兼容')
        media.mkdir(parents=True,exist_ok=True)
        stage=media/('.restore-'+str(uuid.uuid4()));shutil.copytree(source/'media',stage)
        subprocess.run(['pg_restore','--exit-on-error','--single-transaction','--no-owner','--no-acl','--dbname',engine.url.database,str(source/'database.dump')],env=pg_env(engine),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=600)
        require_current_schema(engine)
        if db_fingerprint(con)!=m['tables']:raise BackupError('恢复后的逻辑数据与备份不一致')
        for child in stage.iterdir():os.rename(child,media/child.name)
        stage.rmdir()
        expected={k.removeprefix('media/'):v for k,v in m['files'].items() if k.startswith('media/')}
        if files(media)!=expected:raise BackupError('恢复后的媒体校验不一致')
    result={'backup_id':id,'file_integrity':'passed','database_restore':'passed','media_restore':'passed',
            'all_table_fingerprints':'passed','schema_version':HEAD,'app_version':version(),'manifest_sha256':sha(source/'manifest.json'),'tables':m['tables'],
            'note':'数据库与媒体实际恢复完成；还须启动应用并运行认证、文章和图片读取验收，不能仅凭本报告声称前台验收通过'}
    if report:
        report=Path(report)
        # Never let the report path overwrite a restored file or a backup file.
        resolved=report.absolute()
        if media==resolved or media in resolved.parents or backup_root() in resolved.parents:raise BackupError('报告必须保存到独立位置')
        with report.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    return result

def supervised(action,id=None,report=None):
    command=[sys.executable,'-m','app.backup','_execute',action]
    if id:command+=['--id',id]
    if report:command+=['--report',report]
    process=subprocess.Popen(command,start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    try:stdout,_=process.communicate(timeout=900)
    except BaseException:
        os.killpg(process.pid,signal.SIGKILL);process.wait();raise BackupError('备份/恢复超过安全时限或被中止，写入锁已释放') from None
    if process.returncode:
        try:message=json.loads(stdout)['error']
        except (ValueError,KeyError,TypeError):message='任务失败，未标记成功；检查维护容器及存储状态'
        raise BackupError(message)
    return json.loads(stdout)

def record_drill(id,report):
    # No restore endpoint can set this. An operator supplies the report produced
    # by an actual isolated restore + authenticated application acceptance run.
    if not report:raise BackupError('需要隔离恢复及应用验收报告')
    with backup_lock(id=id):
        m=verify(id);r=json.loads(no_symlinks(Path(report)).read_text())
        expected={'backup_id':id,'file_integrity':'passed','database_restore':'passed','media_restore':'passed',
                  'all_table_fingerprints':'passed','schema_version':m['schema_version'],'app_version':m['app_version'],
                  'manifest_sha256':sha(artifact_path(backup_root(),id)/'manifest.json'),'application_validation':'passed'}
        if any(r.get(k)!=v for k,v in expected.items()) or r.get('tables')!=m['tables']:raise BackupError('恢复报告缺少实际恢复或应用验收证据')
        from .db import SessionLocal
        from .services.write_barrier import writer
        from .services.recovery import db_now
        with writer(engine),SessionLocal() as db:
            row=db.get(recovery_models.BackupArtifact,id)
            if row is None:
                from .maintenance_worker import catalog
                row=catalog(db,m)
            if row.manifest_sha256!=expected['manifest_sha256']:raise BackupError('登记的清单不匹配')
            row.restored_at=db_now(db);row.verified_at=row.restored_at;db.commit()
        return {'backup_id':id,'restore_validation':'passed'}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['init-target','create','verify','restore','record-drill','_execute'])
    parser.add_argument('internal',nargs='?',choices=['create','restore']);parser.add_argument('--id');parser.add_argument('--confirm-independent-storage',action='store_true');parser.add_argument('--confirm-empty-target',action='store_true');parser.add_argument('--report')
    args=parser.parse_args()
    try:
        if args.action=='init-target':
            prepare_local_target()
            print('SSD 本地备份目录已就绪；不会验证极空间 HDD 外部备份任务');return
        if args.action=='create':result=supervised('create',args.id)
        elif args.action=='verify':
            with backup_lock(id=args.id):result=verify(args.id)
        elif args.action=='record-drill':result=record_drill(args.id,args.report)
        elif args.action=='restore':
            if not args.confirm_empty_target:raise BackupError('必须明确确认空目标')
            result=supervised('restore',args.id,args.report)
        else:result=create_backup(args.id) if args.internal=='create' else restore(args.id,True,args.report)
        print(json.dumps(result,ensure_ascii=False))
    except Exception as e:
        # Never print connection URLs, pg stderr, paths or content values.
        if args.action=='_execute':print(json.dumps({'error':safe_error(e)},ensure_ascii=False))
        else:print(safe_error(e),file=sys.stderr)
        raise SystemExit(1)



def prepare_local_target():
    """Maintenance-only setup, never remove/overwrite existing backups or markers."""
    root=backup_root()
    if not root.is_dir():raise BackupError('SSD 备份目录不存在，请在 Docker GUI 创建并挂载专用目录')
    fd=os.open(root/'.operation.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    os.close(fd)

if __name__=='__main__':main()
