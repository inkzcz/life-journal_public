"""Remote tag identity must survive checkout's local peeled-tag behavior."""
import pytest
import json
import subprocess

from scripts.release_preflight import annotated_remote_target
from scripts import release_preflight as gate


def sample():
    reference={'ref':'refs/tags/v5.1.9','object':{'type':'tag','sha':'a'*40}}
    tag={'sha':'a'*40,'tag':'v5.1.9','object':{'type':'commit','sha':'b'*40}}
    return reference,tag


def test_remote_annotated_tag_proof_does_not_depend_on_local_checkout_ref():
    reference,tag=sample()
    # actions/checkout can map its local refs/tags/name directly to the commit.
    # That local convenience ref is not the authoritative server tag object.
    assert annotated_remote_target(reference,tag)==('b'*40,'a'*40)


@pytest.mark.parametrize('change',[
    'lightweight','wrong_name','wrong_object','nested_tag','invalid_commit',
])
def test_wrong_remote_annotation_or_target_is_still_rejected(change):
    reference,tag=sample()
    if change=='lightweight':reference['object']['type']='commit'
    elif change=='wrong_name':tag['tag']='v5.1.8'
    elif change=='wrong_object':tag['sha']='c'*40
    elif change=='nested_tag':tag['object']['type']='tag'
    else:tag['object']['sha']='unverified'
    with pytest.raises(RuntimeError,match='annotated tag'):annotated_remote_target(reference,tag)


def test_dispatch_keeps_application_and_orchestration_commits_distinct(tmp_path,monkeypatch,capsys):
    monkeypatch.chdir(tmp_path);(tmp_path/'licensing').mkdir();(tmp_path/'VERSION').write_text('5.1.9\n')
    (tmp_path/'licensing/BINARY_RELEASE_AUTHORIZATION.json').write_text(json.dumps({
        'binary_publication_approved':True,'repository':gate.REPO,'version':gate.TAG}))
    reference,tag=sample();source='b'*40;orchestration='c'*40
    def api(path):
        if path=='git/ref/tags/v5.1.9':return reference
        if path.startswith('git/tags/'):return tag
        if path=='pulls/2':return {'merged':True,'merge_commit_sha':source}
        return {'workflow_runs':[{'head_sha':sha,'head_branch':'main','event':'push',
                                  'conclusion':'success','id':number} for number,sha in enumerate((source,orchestration),1)]}
    calls=[]
    def run(*args):
        calls.append(args)
        if args==('git','rev-parse','HEAD'):return orchestration
        if args[:2]==('git','show'):return '5.1.9'
        if args[:2]==('git','rev-list'):return source+' '+'d'*40+' '+'e'*40
        if args[:2] in (('git','merge-base'),('git','diff')):return ''
        pytest.fail('Unexpected local tag inspection or mutation')
    monkeypatch.setattr(gate,'api',api);monkeypatch.setattr(gate,'run',run)
    monkeypatch.setattr(gate.subprocess,'run',lambda *a,**k:subprocess.CompletedProcess(a,1,'','gh: Not Found (HTTP 404)'))
    gate.main();receipt=json.loads(capsys.readouterr().out)
    assert receipt['revision']==source and receipt['orchestration_revision']==orchestration
    assert receipt['tag_sha']=='a'*40
    assert not any('tag' in command for command in calls)
