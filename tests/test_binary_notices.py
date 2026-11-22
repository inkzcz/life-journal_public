"""Notice/replace probes are evidence, never a fake redistribution approval."""
import importlib.util
from pathlib import Path

import pytest

from scripts import binary_notices

ROOT=Path(__file__).resolve().parents[1]


def test_actual_python_notice_inventory_preserves_text_and_flags_missing(tmp_path):
    package=tmp_path/'synthetic-1.dist-info';package.mkdir()
    (package/'METADATA').write_text('Name: synthetic\nVersion: 1\nLicense-Expression: MIT\n\n')
    (package/'licenses').mkdir()
    notice=package/'licenses/LICENSE.txt';notice.write_bytes(b'Synthetic upstream\r\n')
    rows=binary_notices.python_packages([tmp_path])
    assert rows[0]['name']=='synthetic' and rows[0]['license_declared']=='MIT'
    assert rows[0]['notices']==[binary_notices.record(notice)]
    assert notice.read_bytes()==b'Synthetic upstream\r\n'
    notice.unlink()
    assert binary_notices.python_packages([tmp_path])[0]['notices']==[]


def test_notice_collector_bounds_oversized_input(tmp_path):
    path=tmp_path/'LICENSE';path.write_bytes(b'x'*(2*1024*1024+1))
    with pytest.raises(ValueError,match='Oversized notice'):binary_notices.record(path)


def probe():
    spec=importlib.util.spec_from_file_location('lgpl_probe',ROOT/'tests/lgpl_replacement_probe.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('key,value',[
    ('RUN_LJ_LGPL_REPLACEMENT_DRILL',''),('POSTGRES_HOST','production.invalid'),
    ('POSTGRES_DB','personal'),('POSTGRES_USER','owner'),
])
def test_lgpl_probe_rejects_unapproved_database_before_connection(key,value):
    env={'RUN_LJ_LGPL_REPLACEMENT_DRILL':'1','POSTGRES_HOST':'db',
         'POSTGRES_DB':'lj_validation','POSTGRES_USER':'lj_validation'}
    env[key]=value
    with pytest.raises(RuntimeError,match='synthetic LGPL'):probe().require_synthetic_environment(env)


def test_replacement_compatible_wrapper_forwards_arguments():
    class Connection:
        def execute(self,*args,**kwargs):return args,kwargs
    scope={'Connection':Connection}
    exec(probe().PATCH,scope)
    assert Connection().execute('SELECT 17',prepare=True)==(('SELECT 17',),{'prepare':True})
    assert scope['__life_journal_replacement_calls__']==1
