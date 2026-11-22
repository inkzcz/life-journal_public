"""Explicit synthetic-only Psycopg LGPL replacement drill, inside maintenance.

Copies the installed library into this process's TemporaryDirectory, changes its
connection method compatibly, and loads that copy in a child interpreter using
the supported pure-Python implementation + system libpq. No installed files,
database rows, roles or schema are modified. Not a corresponding-source audit.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PATCH = '''
# Life Journal synthetic LGPL interface-compatible replacement probe.
__life_journal_replacement_calls__ = 0
_life_journal_original_execute = Connection.execute
def _life_journal_execute(self, *args, **kwargs):
    global __life_journal_replacement_calls__
    __life_journal_replacement_calls__ += 1
    return _life_journal_original_execute(self, *args, **kwargs)
Connection.execute = _life_journal_execute
'''

CHILD = '''
import json, os
from pathlib import Path
import psycopg
assert Path(os.environ['LJ_REPLACEMENT_ROOT']).resolve() in Path(psycopg.__file__).resolve().parents
assert psycopg.pq.__impl__ == 'python'
with psycopg.connect(host='db', dbname='lj_validation', user='lj_validation',
                     password=os.environ['POSTGRES_PASSWORD'], connect_timeout=10) as connection:
    row = connection.execute('SELECT current_database(), current_user, 17').fetchone()
    assert row == ('lj_validation', 'lj_validation', 17)
assert psycopg.__life_journal_replacement_calls__ == 1
print(json.dumps({'modified_library_loaded': True, 'interface_compatible_query': 'passed',
                  'implementation': psycopg.pq.__impl__, 'system_libpq_version': psycopg.pq.version(),
                  'installed_library_unchanged': True}))
'''


def require_synthetic_environment(env):
    if (env.get('RUN_LJ_LGPL_REPLACEMENT_DRILL') != '1'
            or env.get('POSTGRES_HOST') != 'db'
            or env.get('POSTGRES_DB') != 'lj_validation'
            or env.get('POSTGRES_USER') != 'lj_validation'):
        raise RuntimeError('Explicit isolated synthetic LGPL drill required')


def main():
    require_synthetic_environment(os.environ)
    import psycopg
    source = Path(psycopg.__file__).parent
    with tempfile.TemporaryDirectory(prefix='lj-lgpl-replacement-') as directory:
        target = Path(directory) / 'psycopg'
        shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__'))
        with (target / '__init__.py').open('a') as stream:
            stream.write(PATCH)
        env = dict(os.environ, PYTHONPATH=directory, LJ_REPLACEMENT_ROOT=directory,
                   PSYCOPG_IMPL='python', PYTHONDONTWRITEBYTECODE='1')
        process = subprocess.run([sys.executable, '-c', CHILD], env=env,
                                 capture_output=True, text=True, timeout=45)
        if process.returncode:
            # Do not print a connection exception, which can embed connection data.
            raise RuntimeError('LGPL replacement child failed; exit=' + str(process.returncode))
        print(json.dumps(json.loads(process.stdout), sort_keys=True))


if __name__ == '__main__':
    main()
