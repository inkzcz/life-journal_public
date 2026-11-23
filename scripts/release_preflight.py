"""Read-only formal tag gate: owner grant, ordinary PR merge, exact main CI."""
import json
from pathlib import Path
import re
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.release_authorization import REPOSITORY as REPO, RELEASES, read_authorization


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError('Release preflight command failed: '+args[0]+'; exit='+str(result.returncode))
    return result.stdout.strip()


def api(path):
    return json.loads(run('gh', 'api', '--method', 'GET', 'repos/'+REPO+'/'+path))


def annotated_remote_target(reference, tag, version='v5.1.9'):
    """Use the remote tag object even when checkout peels its local ref."""
    if (version not in RELEASES or reference.get('ref') != 'refs/tags/'+version
            or reference.get('object', {}).get('type') != 'tag'
            or not re.fullmatch('[0-9a-f]{40}', reference.get('object', {}).get('sha', ''))
            or tag.get('sha') != reference['object']['sha'] or tag.get('tag') != version
            or tag.get('object', {}).get('type') != 'commit'
            or not re.fullmatch('[0-9a-f]{40}', tag.get('object', {}).get('sha', ''))):
        raise RuntimeError('Remote version must be an annotated tag directly naming a commit')
    return tag['object']['sha'], tag['sha']


def main():
    product = Path('VERSION').read_text().strip()
    version = 'v'+product
    authorization = read_authorization(Path('.'), version)
    pr_number = RELEASES[version][1]
    reference = api('git/ref/tags/'+version)
    if reference.get('object', {}).get('type') != 'tag':
        raise RuntimeError('A remote annotated tag is required')
    revision, tag_sha = annotated_remote_target(reference, api('git/tags/'+reference['object']['sha']), version)
    retained = authorization.get('retained_tag_identity')
    if retained and (retained.get('tag_sha') != tag_sha or retained.get('source_commit') != revision):
        raise RuntimeError('Existing owner-authorized tag identity changed; nothing may be overwritten')
    orchestration = run('git', 'rev-parse', 'HEAD')
    if run('git', 'show', revision+':VERSION') != product:
        raise RuntimeError('Tagged application version mismatch')
    pr = api('pulls/'+str(pr_number))
    if (pr.get('merged') is not True or pr.get('merge_commit_sha') != revision
            or pr.get('base', {}).get('ref') != 'main' or pr.get('draft') is not False):
        raise RuntimeError('Formal tag must identify the authorized ordinary PR main merge commit')
    parents = run('git', 'rev-list', '--parents', '-n', '1', revision).split()
    if len(parents) != 3 or parents[2] != pr.get('head', {}).get('sha'):
        raise RuntimeError('Ordinary merge commit with the exact reviewed PR head required')
    run('git', 'merge-base', '--is-ancestor', revision, 'origin/main')
    if version=='v5.1.10':
        feature=authorization.get('reviewed_feature_head','')
        if not re.fullmatch('[0-9a-f]{40}',feature):raise RuntimeError('Reviewed feature baseline missing')
        run('git','merge-base','--is-ancestor',feature,pr['head']['sha'])
    run('git', 'diff', '--exit-code', revision, orchestration, '--', 'Dockerfile', '.dockerignore',
        'backend/app', 'backend/alembic', 'backend/requirements.txt', 'backend/constraints-release.txt',
        'frontend/src', 'frontend/package.json', 'frontend/package-lock.json', 'frontend/Caddyfile',
        'compose.yaml', 'compose.nas.yaml')
    runs = api('actions/workflows/ci.yml/runs?branch=main&event=push&per_page=100')['workflow_runs']
    def succeeded(sha):
        return [r for r in runs if r['head_sha'] == sha and r['head_branch'] == 'main'
                and r['event'] == 'push' and r['status'] == 'completed' and r['conclusion'] == 'success']
    successful = succeeded(revision)
    if not successful or not succeeded(orchestration):
        raise RuntimeError('Exact merged-main and publication-orchestration CI must succeed')
    checks = api('commits/'+pr['head']['sha']+'/check-runs?per_page=100')['check_runs']
    for name in ('source-and-tests', 'docker-installation', 'windows-toolchain'):
        if not any(c['name'] == name and c['status'] == 'completed' and c['conclusion'] == 'success' for c in checks):
            raise RuntimeError('Exact PR head required check has not succeeded: '+name)
    conflict = subprocess.run(['gh', 'api', '--method', 'GET', 'repos/'+REPO+'/releases/tags/'+version],
                              capture_output=True, text=True, timeout=60)
    if conflict.returncode == 0:
        raise RuntimeError('Release already exists; nothing overwritten')
    if '404' not in conflict.stderr:
        raise RuntimeError('Cannot establish Release absence or permission')
    print(json.dumps({'version': version, 'revision': revision, 'tag_sha': tag_sha,
        'orchestration_revision': orchestration, 'source_pull_request': pr_number,
        'main_ci_run': successful[0]['id'], 'release_absent': True}))


if __name__ == '__main__':
    main()
