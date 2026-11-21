"""Read-only, fail-closed ownership validation for backups, including crash state."""
from pathlib import Path
from sqlalchemy import inspect,select
from .models import ExchangeJob,ExchangeFileOperation
from .jobs import checked,verify_files,digest,NAMES,library_dir


def inventory(db,root):
    staging=checked(Path(root)/'.exchange-v1')
    if not inspect(db.connection()).has_table('exchange_jobs'):
        if staging.exists():raise RuntimeError('旧数据库存在未知交换临时目录，备份已停止')
        return set()
    jobs={row.id:row for row in db.scalars(select(ExchangeJob))}
    pending=set()
    if staging.exists():
        if not staging.is_dir():raise RuntimeError('交换临时根目录状态异常')
        for folder in staging.iterdir():
            checked(folder)
            row=jobs.get(folder.name)
            if row is None or not folder.is_dir():raise RuntimeError('未知交换任务目录，备份已停止')
            entries={e['id']:e for e in row.file_manifest['media'].values()}
            for media in folder.iterdir():
                checked(media)
                entry=entries.get(media.name)
                if entry is None or not media.is_dir():raise RuntimeError('未知交换照片目录，备份已停止')
                if set(entry['files'])!=NAMES:raise RuntimeError('交换文件日志不完整')
                # A process can stop between individually fsynced staging files.
                # Every existing byte must match the durable owner journal;
                # missing staging bytes are retained for explicit same-file retry.
                for p in media.iterdir():
                    checked(p)
                    if p.name not in NAMES or not p.is_file() or digest(p.read_bytes())!=entry['files'][p.name]:
                        raise RuntimeError('交换临时文件完整性异常，备份已停止')
    for op in db.scalars(select(ExchangeFileOperation)):
        row=jobs.get(op.job_id)
        if row is None:raise RuntimeError('交换文件日志缺少所属任务')
        if row.state!='confirming' or op.state not in {'prepared','files_ready'}:continue
        for entry in op.manifest['media'].values():
            target=library_dir(root,entry['id'])
            source=checked(staging/row.id/entry['id'])
            if target.exists()==source.exists():raise RuntimeError('确认中的交换照片目录状态不明确，备份已停止')
            verify_files(target if target.exists() else source,entry['files'])
            if target.exists():pending.add(entry['id'])
    return pending
