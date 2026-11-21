"""Opt-in real BuildKit check using synthetic, disposable context only."""
import json
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.skipif(not os.getenv('TEST_BUILDX_BUILDER'),reason='Requires an explicitly selected disposable local builder')
def test_context_excludes_private_directories_even_after_parent_exceptions(tmp_path):
    root=Path(__file__).resolve().parents[1]
    (tmp_path/'.dockerignore').write_bytes((root/'.dockerignore').read_bytes())
    forbidden=['.env','frontend/node_modules/sentinel','frontend/media/sentinel',
               'backend/media/sentinel','backend/backups/sentinel',
               'backend/app/__pycache__/sentinel.pyc','backend/app/secret.key',
               'backend/app/private.sqlite3','frontend/src/media/sentinel']
    required=['frontend/src/main.ts','frontend/package.json',
              'backend/app/main.py','backend/alembic/env.py','backend/requirements.txt']
    for name in forbidden+required:
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text('synthetic-context-only')
    script='import json; from pathlib import Path; print("CONTEXT_RESULT="+json.dumps({p:Path("/context",p).exists() for p in '+repr(forbidden+required)+'}))'
    dockerfile=tmp_path/'Dockerfile'
    dockerfile.write_text('FROM python:3.12-slim-bookworm\nRUN --network=none --mount=type=bind,target=/context,readonly python -c '+json.dumps(script)+'\n')
    result=subprocess.run(['docker','buildx','build','--builder',os.environ['TEST_BUILDX_BUILDER'],
                           '--progress','plain','--output','type=cacheonly',str(tmp_path)],
                          capture_output=True,text=True,timeout=90)
    assert result.returncode==0,'Context probe failed; raw build output withheld'
    records=[line.split('CONTEXT_RESULT=',1)[1] for line in result.stderr.splitlines() if 'CONTEXT_RESULT={' in line]
    assert len(records)==1
    actual=json.loads(records[0])
    assert all(not actual[name] for name in forbidden)
    assert all(actual[name] for name in required)
