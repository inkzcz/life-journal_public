"""Exact remote annotation, PR ancestry and complete CI; no release mutations."""
import json
import subprocess
import pytest
from scripts import release_preflight as gate


def sample(version='v5.1.9'):
    return ({'ref':'refs/tags/'+version,'object':{'type':'tag','sha':'a'*40}},
        {'sha':'a'*40,'tag':version,'object':{'type':'commit','sha':'b'*40}})


@pytest.mark.parametrize('version',['v5.1.9','v5.1.10','v5.1.11'])
def test_remote_annotation_does_not_depend_on_local_peeled_ref(version):
    assert gate.annotated_remote_target(*sample(version),version)==('b'*40,'a'*40)


@pytest.mark.parametrize('change',['lightweight','wrong_name','wrong_object','nested_tag','invalid_commit'])
def test_wrong_remote_annotation_or_target_is_still_rejected(change):
    reference,tag=sample('v5.1.10')
    if change=='lightweight':reference['object']['type']='commit'
    elif change=='wrong_name':tag['tag']='v5.1.9'
    elif change=='wrong_object':tag['sha']='c'*40
    elif change=='nested_tag':tag['object']['type']='tag'
    else:tag['object']['sha']='unverified'
    with pytest.raises(RuntimeError,match='annotated tag'):gate.annotated_remote_target(reference,tag,'v5.1.10')


@pytest.fixture
def preflight(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);(tmp_path/'VERSION').write_text('5.1.10\n')
    folder=tmp_path/'licensing';folder.mkdir()
    authority={'format':'life-journal-binary-release-authorization-v1','binary_publication_approved':True,
        'repository':gate.REPO,'version':'v5.1.10','source_pull_request':4,'reviewed_feature_head':'1'*40,
        'registry_push_approved':False,'nas_access_approved':False,'private_repository_changes_approved':False,
        'owner_confirmation_reference':'Synthetic owner fixture'}
    (folder/'BINARY_RELEASE_v5.1.10_AUTHORIZATION.json').write_text(json.dumps(authority))
    reference,tag=sample('v5.1.10');source='b'*40;orchestration='c'*40;head='e'*40
    state={'pr':{'merged':True,'merge_commit_sha':source,'base':{'ref':'main'},'draft':False,'head':{'sha':head}},
        'runs':[{'head_sha':sha,'head_branch':'main','event':'push','status':'completed',
                 'conclusion':'success','id':number} for number,sha in enumerate((source,orchestration),1)],
        'checks':[{'name':name,'status':'completed','conclusion':'success'} for name in ('source-and-tests','docker-installation','windows-toolchain')],
        'parents':[source,'d'*40,head],'release_returncode':1,'release_error':'gh: Not Found (HTTP 404)'}
    calls=[]
    def api(path):
        if path=='git/ref/tags/v5.1.10':return reference
        if path.startswith('git/tags/'):return tag
        if path=='pulls/4':return state['pr']
        if path.startswith('commits/'):return {'check_runs':state['checks']}
        if path.startswith('actions/'):return {'workflow_runs':state['runs']}
        pytest.fail('Unexpected API request: '+path)
    def run(*args):
        calls.append(args)
        if args==('git','rev-parse','HEAD'):return orchestration
        if args[:2]==('git','show'):return '5.1.10'
        if args[:2]==('git','rev-list'):return ' '.join(state['parents'])
        if args[:2] in (('git','merge-base'),('git','diff')):return ''
        pytest.fail('Unexpected local tag inspection or mutation')
    monkeypatch.setattr(gate,'api',api);monkeypatch.setattr(gate,'run',run)
    monkeypatch.setattr(gate.subprocess,'run',lambda *a,**k:subprocess.CompletedProcess(a,state['release_returncode'],'',state['release_error']))
    return state,calls


def test_dispatch_keeps_application_and_orchestration_commits_distinct(preflight,capsys):
    state,calls=preflight;gate.main();receipt=json.loads(capsys.readouterr().out)
    assert receipt['revision']=='b'*40 and receipt['orchestration_revision']=='c'*40
    assert receipt['tag_sha']=='a'*40 and receipt['version']=='v5.1.10' and receipt['source_pull_request']==4
    assert not any('tag' in command or 'push' in command for command in calls)


@pytest.mark.parametrize('failure',['not_merged','wrong_merge','draft','wrong_base','wrong_parent','squash',
    'old_main_ci','failed_main_ci','running_main_ci','missing_pr_check','skipped_pr_check',
    'failed_pr_check','existing_release','permission_unknown'])
def test_formal_gate_rejects_unverified_release_identity_or_checks(preflight,failure):
    state,_=preflight
    if failure=='not_merged':state['pr']['merged']=False
    elif failure=='wrong_merge':state['pr']['merge_commit_sha']='f'*40
    elif failure=='draft':state['pr']['draft']=True
    elif failure=='wrong_base':state['pr']['base']['ref']='other'
    elif failure=='wrong_parent':state['parents'][2]='f'*40
    elif failure=='squash':state['parents'].pop()
    elif failure=='old_main_ci':state['runs'][0]['head_sha']='f'*40
    elif failure=='failed_main_ci':state['runs'][0]['conclusion']='failure'
    elif failure=='running_main_ci':state['runs'][0]['status']='in_progress'
    elif failure=='missing_pr_check':state['checks'].pop()
    elif failure=='skipped_pr_check':state['checks'][0]['conclusion']='skipped'
    elif failure=='failed_pr_check':state['checks'][1]['conclusion']='failure'
    elif failure=='existing_release':state['release_returncode']=0
    else:state['release_error']='gh: Forbidden (HTTP 403)'
    with pytest.raises(RuntimeError):gate.main()
