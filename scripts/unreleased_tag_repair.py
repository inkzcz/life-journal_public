"""Read-only, single-version eligibility receipt; never deletes or creates refs."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.release_authorization import REPOSITORY, read_authorization


def get(path, optional=False):
    result = subprocess.run(['gh', 'api', '--method', 'GET', ('repos/'+REPOSITORY+'/'+path).rstrip('/')],
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        if optional and '404' in result.stderr:
            return None
        raise RuntimeError('Cannot verify tag repair eligibility: GitHub GET failed')
    return json.loads(result.stdout)


def validate(state, authority, replacement):
    repair = authority['unreleased_tag_repair']
    ref, tag = state['reference'], state['tag']
    if (ref.get('ref') != 'refs/tags/v5.1.11' or ref.get('object', {}).get('type') != 'tag'
            or ref['object'].get('sha') != repair['original_tag_sha']
            or tag.get('sha') != repair['original_tag_sha'] or tag.get('tag') != 'v5.1.11'
            or tag.get('object', {}).get('type') != 'commit'
            or tag['object'].get('sha') != repair['original_source_commit']):
        raise ValueError('Exact original unreleased tag identity changed; stop')
    if (state['release'] is not None or state['next_release'] is not None
            or state['next_tag'] is not None):
        raise ValueError('Release or conflicting v5.1.12 identity exists; stop')
    if state['active_runs'] or state['known_external_dependencies']:
        raise ValueError('Active workflow or known external dependency; stop')
    if (state['old_artifacts'].get('total_count') != 0
            or state['old_run'].get('conclusion') != 'failure'
            or state['old_run'].get('status') != 'completed'
            or state['old_run'].get('head_sha') != repair['original_source_commit']
            or any(r.get('head_branch') == 'v5.1.11' and r.get('conclusion') == 'success'
                   for r in state['formal_runs'])):
        raise ValueError('Prior formal delivery or unresolved artifact evidence; stop')
    pr = state['pr']
    if (not re.fullmatch('[0-9a-f]{40}', replacement) or state['main']['sha'] != replacement
            or pr.get('merged') is not True or pr.get('draft') is not False
            or pr.get('merge_commit_sha') != replacement or pr.get('base', {}).get('ref') != 'main'):
        raise ValueError('Final authorized ordinary main merge required')
    if not any(r.get('head_sha') == replacement and r.get('head_branch') == 'main'
               and r.get('event') == 'push' and r.get('status') == 'completed'
               and r.get('conclusion') == 'success' for r in state['main_runs']):
        raise ValueError('Exact final main CI must succeed')
    for name in ('source-and-tests', 'docker-installation', 'windows-toolchain'):
        if not any(c.get('name') == name and c.get('status') == 'completed'
                   and c.get('conclusion') == 'success' for c in state['checks']):
            raise ValueError('Exact repair PR checks must succeed')
    return {'eligible': True, 'repository': REPOSITORY, 'version': 'v5.1.11',
            'old_tag_sha': repair['original_tag_sha'], 'old_source_commit': repair['original_source_commit'],
            'replacement_commit': replacement, 'source_pull_request': authority['source_pull_request'],
            'known_external_dependencies': [], 'mutations_performed': False,
            'limitations': 'Known accessible repository/Actions/distribution evidence only; unknown private clones cannot be enumerated.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replacement-commit', required=True)
    args = parser.parse_args()
    authority = read_authorization(Path('.'), 'v5.1.11')
    reference = get('git/ref/tags/v5.1.11')
    tag = get('git/tags/'+reference['object']['sha'])
    pr = get('pulls/'+str(authority['source_pull_request']))
    repo = get('')
    state = {'reference': reference, 'tag': tag, 'pr': pr,
             'release': get('releases/tags/v5.1.11', True),
             'next_release': get('releases/tags/v5.1.12', True),
             'next_tag': get('git/ref/tags/v5.1.12', True), 'main': get('commits/main'),
             'active_runs': [r for status in ('in_progress','queued','waiting','pending','requested')
                             for r in get('actions/runs?status='+status+'&per_page=100')['workflow_runs']],
             'old_run': get('actions/runs/45618008729'),
             'old_artifacts': get('actions/runs/45618008729/artifacts'),
             'formal_runs': get('actions/workflows/release.yml/runs?per_page=100')['workflow_runs'],
             'main_runs': get('actions/workflows/ci.yml/runs?branch=main&event=push&per_page=100')['workflow_runs'],
             'checks': get('commits/'+pr['head']['sha']+'/check-runs?per_page=100')['check_runs'],
             'known_external_dependencies': ['fork requires manual review'] if repo['forks_count'] else []}
    # Independently verify ordinary merge ancestry, not only PR metadata.
    parents = subprocess.check_output(['git','rev-list','--parents','-n','1',args.replacement_commit],text=True).split()
    if len(parents) != 3 or parents[2] != pr['head']['sha']:
        raise ValueError('Ordinary merge with exact repair PR head required')
    subprocess.run(['git','merge-base','--is-ancestor',authority['reviewed_feature_head'],args.replacement_commit],check=True)
    print(json.dumps(validate(state, authority, args.replacement_commit), indent=2))


if __name__ == '__main__':
    main()
