"""No host ownership is changed: verify the narrowly scoped bootstrap decisions."""
import os,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'backend'))
from app.container_entrypoint import prepare_empty_directory

def test_no_arbitrary_path_or_symlink_is_accepted(tmp_path,monkeypatch):
    with pytest.raises(RuntimeError,match='不允许'):prepare_empty_directory(tmp_path)
    monkeypatch.setattr(Path,'is_symlink',lambda _:True)
    with pytest.raises(RuntimeError,match='符号链接'):prepare_empty_directory('/data/media')

def test_nonempty_data_is_never_chowned(monkeypatch):
    from types import SimpleNamespace
    calls=[]
    monkeypatch.setattr(Path,'is_symlink',lambda _:False)
    monkeypatch.setattr(Path,'is_dir',lambda _:True)
    monkeypatch.setattr(Path,'stat',lambda _:SimpleNamespace(st_uid=0))
    monkeypatch.setattr(Path,'iterdir',lambda _:iter([Path('existing-photo')]))
    monkeypatch.setattr(os,'chown',lambda *args:calls.append(args))
    monkeypatch.setattr(os,'chmod',lambda *args:calls.append(args))
    prepare_empty_directory('/data/media');prepare_empty_directory('/backups')
    assert not calls

def test_empty_directory_initialization_is_bounded(monkeypatch):
    from types import SimpleNamespace
    calls=[]
    monkeypatch.setattr(Path,'is_symlink',lambda _:False)
    monkeypatch.setattr(Path,'is_dir',lambda _:True)
    monkeypatch.setattr(Path,'stat',lambda _:SimpleNamespace(st_uid=0))
    monkeypatch.setattr(Path,'iterdir',lambda _:iter([]))
    monkeypatch.setattr(os,'chown',lambda *args:calls.append(('chown',args)))
    monkeypatch.setattr(os,'chmod',lambda *args:calls.append(('chmod',args)))
    prepare_empty_directory('/data/media')
    assert calls==[('chown',(Path('/data/media'),10001,10001)),('chmod',(Path('/data/media'),0o700))]
