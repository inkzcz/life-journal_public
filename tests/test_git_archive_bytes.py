"""Reproduce Windows archive CRLF conversion; never normalize verified input.
Run on Linux and native Windows. Synthetic Git objects include exact binary CRLF.
"""
import hashlib,subprocess,zipfile
from pathlib import Path
import pytest
from scripts import release_source as authority

@pytest.fixture
def archive_repo(tmp_path):
    repo=tmp_path/'repo';repo.mkdir()
    subprocess.run(['git','init','-q',str(repo)],check=True)
    content={'.env.example':b'EXAMPLE=synthetic\nNEXT=synthetic\n',
             'script.py':b'print("synthetic")\n',
             'raw.bin':b'\x00binary\r\nexact\xff',
             '.gitattributes':b'/script.py text eol=lf\n/raw.bin -text\n'}
    for path,data in content.items():(repo/path).write_bytes(data)
    # Git input bytes are explicit; don't inherit the test host's global EOL.
    subprocess.run(['git','-C',str(repo),'-c','core.autocrlf=false','add','.'],check=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Synthetic','-c','user.email=synthetic@example.invalid','commit','-qm','fixture'],check=True)
    files={p:{'mode':'100644','oid':authority.blob_hash(data),'sha256':hashlib.sha256(data).hexdigest()} for p,data in content.items()}
    manifest={'files':files,'tree':authority.tree_oid(files)}
    assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD^{tree}'],text=True).strip()==manifest['tree']
    return repo,content,manifest


def archive(repo,output,fixed):
    # Simulate the failing Windows host even when this regression runs on Linux.
    options=['-c','core.autocrlf=true','-c','core.eol=crlf']
    if fixed:options+=['-c','core.autocrlf=false','-c','core.eol=lf']
    subprocess.run(['git','-C',str(repo),*options,'archive','--format=zip','--output',str(output),'HEAD'],check=True)
    root=output.with_suffix('');root.mkdir()
    with zipfile.ZipFile(output) as z:z.extractall(root)
    return root


def test_unpinned_windows_archive_reproduces_strict_env_rejection(archive_repo,tmp_path):
    repo,content,manifest=archive_repo;root=archive(repo,tmp_path/'unfixed.zip',False)
    assert (root/'.env.example').read_bytes()==content['.env.example'].replace(b'\n',b'\r\n')
    # eol=lf protects script.py but does not cover .env.example.
    assert (root/'script.py').read_bytes()==content['script.py']
    with pytest.raises(ValueError,match=r'源码校验失败：\.env\.example'):authority.verify_tree(root,manifest)


def test_command_scoped_lf_archive_matches_every_git_blob_and_preserves_binary(archive_repo,tmp_path):
    repo,content,manifest=archive_repo;root=archive(repo,tmp_path/'fixed.zip',True)
    for path,data in content.items():
        blob=subprocess.check_output(['git','-C',str(repo),'show','HEAD:'+path])
        assert (root/path).read_bytes()==blob==data
    authority.verify_tree(root,manifest)


def test_verifier_still_rejects_crlf_tampering_after_fixed_archive(archive_repo,tmp_path):
    repo,content,manifest=archive_repo;root=archive(repo,tmp_path/'tampered.zip',True)
    (root/'.env.example').write_bytes(content['.env.example'].replace(b'\n',b'\r\n'))
    with pytest.raises(ValueError,match=r'源码校验失败：\.env\.example'):authority.verify_tree(root,manifest)
