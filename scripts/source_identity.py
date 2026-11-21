"""Local Git/ZIP provenance, without network access or invented Git evidence."""
import hashlib
import shutil
import subprocess
from pathlib import Path
from scripts.release import SHA


def identify(root, revision=None):
    root=Path(root)
    if (root/'.git').exists():
        if not shutil.which('git'):raise ValueError('Git checkout detected; install Git, do not pretend this is a ZIP')
        def git(*args):
            return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True,text=True,timeout=60).stdout.strip()
        actual=git('rev-parse','HEAD')
        if not SHA.fullmatch(actual):raise ValueError('Git HEAD is not a full SHA')
        if revision and revision!=actual:raise ValueError('Requested revision does not match checkout')
        if git('status','--porcelain'):raise ValueError('Commit or stash source changes before building a traceable image')
        return {'revision':actual,'revision_source':'git-head','revision_verified':True,'build_identity':actual,'git_worktree_clean':True,'source_tree_sha256':None}
    if not revision or not SHA.fullmatch(revision):raise ValueError('ZIP source requires --revision with a full 40-character lowercase SHA; it is NOT Git-verified')
    h=hashlib.sha256()
    for context in ('backend','frontend'):
        for path in sorted((root/context).rglob('*')):
            rel=path.relative_to(root/context)
            if any(p in {'node_modules','dist','.git','__pycache__','.pytest_cache'} or p.startswith('.env') for p in rel.parts) or path.suffix=='.pyc':continue
            if path.is_symlink():raise ValueError('ZIP build inputs must not contain symbolic links')
            if path.is_file():
                h.update(path.relative_to(root).as_posix().encode()+b'\0')
                h.update(hashlib.sha256(path.read_bytes()).digest())
    return {'revision':revision,'revision_source':'user-provided-zip','revision_verified':False,'build_identity':h.hexdigest()[:40],'git_worktree_clean':None,'source_tree_sha256':h.hexdigest()}
