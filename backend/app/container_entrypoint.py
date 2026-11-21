"""Initialize ownership of NEW EMPTY bind directories, then drop root forever.
Never recurse, remove files, change ownership of nonempty data, or accept web paths.
The application/worker runs as UID/GID10001; root is only for initial empty mounts.
"""
import os,sys
from pathlib import Path
UID=10001

def prepare_empty_directory(path):
    path=Path(path)
    if path not in {Path('/data/media'),Path('/backups')}:raise RuntimeError('不允许初始化此目录')
    if any(p.is_symlink() for p in [path,*path.parents]):raise RuntimeError('数据目录不能是符号链接')
    if not path.is_dir():return
    if path.stat().st_uid==UID:return
    # Existing data is never chowned/chmodded. The application reports write
    # permission failures so the owner can review, instead of changing old data.
    if next(path.iterdir(),None) is not None:return
    os.chown(path,UID,UID)
    os.chmod(path,0o700)

def main():
    if len(sys.argv)<2:raise SystemExit('缺少启动命令')
    if os.geteuid()==0:
        role=os.getenv('CONTAINER_ROLE','')
        if role=='api':prepare_empty_directory('/data/media')
        elif role=='maintenance':prepare_empty_directory('/backups')
        elif role=='web':pass  # Web has no media/backup mounts to prepare.
        else:raise SystemExit('未知应用角色，拒绝以root启动业务')
        os.setgroups([]);os.setgid(UID);os.setuid(UID)
    os.umask(0o077)
    os.execvp(sys.argv[1],sys.argv[1:])
if __name__=='__main__':main()
