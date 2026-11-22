"""Read-only formal tag gate: owner authorization, PR #2 merge, successful main CI.

Creates/updates nothing. A release workflow may publish only after this succeeds.
"""
import json
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


def main():
    authorization=json.loads(Path('licensing/BINARY_RELEASE_AUTHORIZATION.json').read_text())
    if not (authorization['binary_publication_approved'] is True
            and authorization['repository']==REPO and authorization['version']==TAG):
        raise RuntimeError('Owner binary publication authorization is missing')
    if Path('VERSION').read_text().strip()!='5.1.9':
        raise RuntimeError('Product version mismatch')
    if run('git','cat-file','-t','refs/tags/'+TAG)!='tag':
        raise RuntimeError('A new annotated tag is required')
    revision=run('git','rev-parse','refs/tags/'+TAG+'^{commit}')
    if revision!=run('git','rev-parse','HEAD'):
        raise RuntimeError('Tag/source checkout mismatch')
    pr=api('pulls/2')
    if pr.get('merged') is not True or pr.get('merge_commit_sha')!=revision:
        raise RuntimeError('Formal tag must identify the ordinary PR #2 main merge commit')
    parents=run('git','rev-list','--parents','-n','1',revision).split()
    if len(parents)!=3:
        raise RuntimeError('Ordinary merge commit with two parents required')
    run('git','merge-base','--is-ancestor',revision,'origin/main')
    runs=api('actions/workflows/ci.yml/runs?branch=main&event=push&per_page=100')['workflow_runs']
    successful=[r for r in runs if r['head_sha']==revision and r['head_branch']=='main'
                and r['event']=='push' and r['conclusion']=='success']
    if not successful:
        raise RuntimeError('Exact merged-main CI has not succeeded')
    conflict=subprocess.run(['gh','api','--method','GET','repos/'+REPO+'/releases/tags/'+TAG],capture_output=True,text=True,timeout=60)
    if conflict.returncode==0:
        raise RuntimeError('Release already exists; nothing overwritten')
    if '404' not in conflict.stderr:
        raise RuntimeError('Cannot establish Release absence or permission')
    print(json.dumps({'revision':revision,'tag_sha':run('git','rev-parse','refs/tags/'+TAG),
                      'main_ci_run':successful[0]['id'],'release_absent':True}))


if __name__=='__main__':
    main()
