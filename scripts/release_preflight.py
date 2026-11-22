"""Read-only formal tag gate: owner authorization, PR #2 merge, successful main CI.

Creates/updates nothing. A release workflow may publish only after this succeeds.
"""
import json
import re
from pathlib import Path
import subprocess


REPO='inkzcz/life-journal_public'
TAG='v5.1.9'


def run(*args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=60)
    if result.returncode:
        raise RuntimeError('Release preflight command failed: '+args[0]+'; exit='+str(result.returncode))
    return result.stdout.strip()


def api(path):
    return json.loads(run('gh','api','--method','GET','repos/'+REPO+'/'+path))


def annotated_remote_target(reference,tag):
    """The REST ref preserves the tag object even when checkout peels its ref."""
    if (reference.get('ref')!='refs/tags/'+TAG
            or reference.get('object',{}).get('type')!='tag'
            or not re.fullmatch('[0-9a-f]{40}',reference.get('object',{}).get('sha',''))
            or tag.get('sha')!=reference['object']['sha'] or tag.get('tag')!=TAG
            or tag.get('object',{}).get('type')!='commit'
            or not re.fullmatch('[0-9a-f]{40}',tag.get('object',{}).get('sha',''))):
        raise RuntimeError('Remote v5.1.9 must be an annotated tag directly naming a commit')
    return tag['object']['sha'],tag['sha']


def main():
    authorization=json.loads(Path('licensing/BINARY_RELEASE_AUTHORIZATION.json').read_text())
    if not (authorization['binary_publication_approved'] is True
            and authorization['repository']==REPO and authorization['version']==TAG):
        raise RuntimeError('Owner binary publication authorization is missing')
    if Path('VERSION').read_text().strip()!='5.1.9':
        raise RuntimeError('Product version mismatch')
    reference=api('git/ref/tags/'+TAG)
    if reference.get('object',{}).get('type')!='tag':
        raise RuntimeError('A remote annotated tag is required')
    revision,tag_sha=annotated_remote_target(reference,api('git/tags/'+reference['object']['sha']))
    retained=authorization.get('retained_tag_identity')
    if retained and (retained.get('tag_sha')!=tag_sha or retained.get('source_commit')!=revision):
        raise RuntimeError('Existing owner-authorized tag identity changed; nothing may be overwritten')
    orchestration=run('git','rev-parse','HEAD')
    if run('git','show',revision+':VERSION')!='5.1.9':
        raise RuntimeError('Tagged application version mismatch')
    pr=api('pulls/2')
    if pr.get('merged') is not True or pr.get('merge_commit_sha')!=revision:
        raise RuntimeError('Formal tag must identify the ordinary PR #2 main merge commit')
    parents=run('git','rev-list','--parents','-n','1',revision).split()
    if len(parents)!=3:
        raise RuntimeError('Ordinary merge commit with two parents required')
    run('git','merge-base','--is-ancestor',revision,'origin/main')
    run('git','diff','--exit-code',revision,orchestration,'--','Dockerfile','.dockerignore',
        'backend/app','backend/alembic','backend/requirements.txt','backend/constraints-release.txt',
        'frontend/src','frontend/package.json','frontend/package-lock.json','frontend/Caddyfile',
        'compose.yaml','compose.nas.yaml')
    runs=api('actions/workflows/ci.yml/runs?branch=main&event=push&per_page=100')['workflow_runs']
    successful=[r for r in runs if r['head_sha']==revision and r['head_branch']=='main'
                and r['event']=='push' and r['conclusion']=='success']
    if not successful:
        raise RuntimeError('Exact merged-main CI has not succeeded')
    if not any(r['head_sha']==orchestration and r['head_branch']=='main'
               and r['event']=='push' and r['conclusion']=='success' for r in runs):
        raise RuntimeError('Exact publication-orchestration main CI has not succeeded')
    conflict=subprocess.run(['gh','api','--method','GET','repos/'+REPO+'/releases/tags/'+TAG],capture_output=True,text=True,timeout=60)
    if conflict.returncode==0:
        raise RuntimeError('Release already exists; nothing overwritten')
    if '404' not in conflict.stderr:
        raise RuntimeError('Cannot establish Release absence or permission')
    print(json.dumps({'revision':revision,'tag_sha':tag_sha,'orchestration_revision':orchestration,
                      'main_ci_run':successful[0]['id'],'release_absent':True}))


if __name__=='__main__':
    main()
