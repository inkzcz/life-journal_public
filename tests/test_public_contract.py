"""Public snapshot keeps the complete candidate and one business image contract."""
from pathlib import Path
import json
import re

import yaml

ROOT=Path(__file__).resolve().parents[1]


def distribution_root():
    return ROOT/'open_source/template' if (ROOT/'open_source/template').is_dir() else ROOT


def test_four_roles_reuse_one_business_image_and_never_pull_implicitly():
    compose=yaml.safe_load((distribution_root()/'compose.yaml').read_text())
    services=compose['services'];assert set(services)=={'db','api','web','maintenance'}
    assert len({services[r]['image'] for r in ('api','web','maintenance')})==1
    for role in ('api','web','maintenance'):
        assert services[role]['command']==[role]
        assert services[role]['pull_policy']=='never' and not services[role].get('build')
        assert not any('docker.sock' in str(v) for v in services[role].get('volumes',[]))
    assert services['db']['pull_policy']=='never' and 'POSTGRES_IMAGE:?' in services['db']['image']
    assert not any(services[r].get('ports') for r in ('db','api','maintenance'))
    assert services['api']['depends_on']['maintenance']['condition']=='service_healthy'
    assert services['maintenance']['depends_on']['db']['condition']=='service_healthy'
    assert services['web']['depends_on']['api']['condition']=='service_healthy'


def test_candidate_features_and_migrations_are_present():
    assert (ROOT/'VERSION').read_text().strip()=='5.1.9'
    for name in ('backend/app/calendar','backend/app/exchange','backend/app/routers/experiences.py',
                 'backend/app/services/experiences.py','backend/app/routers/photo_albums.py',
                 'backend/app/services/photo_stream.py',
                 'backend/alembic/versions/0019_unified_experiences.py',
                 'backend/alembic/versions/0020_photo_albums.py',
                 'backend/alembic/versions/0021_anniversary_calendar.py'):
        assert (ROOT/name).exists(),name
    docker=(ROOT/'Dockerfile').read_text()
    assert 'FROM python:3.12-slim-bookworm AS business' in docker
    assert 'COPY --from=frontend-build /src/dist /srv' in docker
    assert 'postgresql-17 postgresql-client-17' in docker
    assert 'rm -f /etc/ssl/private/ssl-cert-snakeoil.key' in docker


def test_public_workflow_is_read_only_pinned_and_cannot_publish():
    path=distribution_root()/'.github/workflows/ci.yml'
    data=yaml.safe_load(path.read_text());assert data['permissions']=={'contents':'read'}
    for job in data['jobs'].values():
        for step in job['steps']:
            if 'uses' in step:assert re.fullmatch(r'[^@]+@[0-9a-f]{40}',step['uses'])
            command=step.get('run','')
            assert '\\"' not in command
            assert not any(text in command for text in ('docker push','gh release','gh repo create'))
    text=path.read_text()
    assert 'pull_request_target' not in text and 'upload-artifact@' not in text
    assert '--require-license' in text and '--redact=100' in text
