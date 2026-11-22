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
    assert re.search(r'FROM python:3\.12-slim-bookworm@sha256:[0-9a-f]{64} AS runtime-base',docker)
    assert 'FROM runtime-base AS business' in docker and 'FROM runtime-base AS python-build' in docker
    assert '--no-binary=psycopg-c' in docker and 'COPY --from=python-build /opt/venv /opt/venv' in docker
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
    assert 'pull_request_target' not in text
    uploads=[step for job in data['jobs'].values() for step in job['steps']
             if step.get('uses','').startswith('actions/upload-artifact@')]
    assert len(uploads)==1
    upload=uploads[0]
    assert "github.repository == 'inkzcz/life-journal_public'" in upload['if']
    assert "github.event_name == 'push'" in upload['if']
    paths=upload['with']['path'].splitlines()
    assert len(paths)==10 and all(p.startswith('${{ runner.temp }}/release-assets/') for p in paths)
    assert not any('*' in p or '..' in p for p in paths)
    assert sum(p.endswith('-amd64.tar') for p in paths)==1
    assert upload['with']['include-hidden-files'] is False
    steps=data['jobs']['docker-installation']['steps']
    assert next(i for i,s in enumerate(steps) if 'prepare_distribution.py' in s.get('run',''))<steps.index(upload)
    assert '--require-license' in text and '--redact=100' in text


def test_formal_release_is_scoped_to_owner_tag_and_isolates_write_token():
    document=yaml.safe_load((ROOT/'.github/workflows/release.yml').read_text())
    assert document['permissions']=={'contents':'read','actions':'read','pull-requests':'read'}
    jobs=document['jobs']
    assert jobs['build']['needs']=='preflight' and jobs['build']['permissions']=={'contents':'read'}
    assert jobs['build']['with']['release_version']=='v5.1.9'
    assert jobs['build']['with']['source_revision']=='${{ needs.preflight.outputs.revision }}'
    assert jobs['build']['with']['annotated_tag_sha']=='${{ needs.preflight.outputs.tag_sha }}'
    publish=jobs['publish']
    assert publish['needs']==['preflight','build'] and publish['permissions']=={'contents':'write','actions':'read'}
    assert "github.ref == 'refs/tags/v5.1.9'" in publish['if']
    assert "github.ref == 'refs/heads/main'" in publish['if'] and "github.event_name == 'workflow_dispatch'" in publish['if']
    assert not any(s.get('uses','').startswith('actions/checkout') for s in publish['steps'])
    for job in jobs.values():
        for step in job.get('steps',[]):
            if 'uses' in step:assert re.fullmatch(r'[^@]+@[0-9a-f]{40}',step['uses'])
    body='\n'.join(s.get('run','') for s in publish['steps'])
    assert 'gh release create v5.1.9 --verify-tag' in body
    assert '--prerelease=false' in body and '--draft=false' in body
    assert 'gh release download v5.1.9' in body and 'sha256sum --check' in body
    assert not any(s in body for s in ('docker push','--force','--clobber','gh release edit'))


def test_formal_source_uses_verified_tag_worktree_not_orchestration_head():
    document=yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())
    steps=document['jobs']['docker-installation']['steps']
    identity=next(s for s in steps if s.get('id')=='identity')['run']
    assert 'git cat-file -t "$ANNOTATED_TAG_SHA"' in identity
    assert 'git worktree add --detach "$app_root" "$SOURCE_REVISION"' in identity
    assert 'python "$app_root/scripts/release_local.py"' in identity
    assert 'git tag' not in identity and 'git push' not in identity
    package=next(s['run'] for s in steps if 'prepare_distribution.py' in s.get('run',''))
    assert '--root "$APP_ROOT" --orchestration-root .' in package
