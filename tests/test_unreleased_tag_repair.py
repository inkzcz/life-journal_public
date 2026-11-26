"""Synthetic read-only eligibility checks; never modify refs or call GitHub."""
import copy
from pathlib import Path
import pytest
from scripts.release_authorization import read_authorization, validate_authorization
from scripts.unreleased_tag_repair import validate

ROOT=Path(__file__).resolve().parents[1]

def sample():
    a=read_authorization(ROOT,'v5.1.11');r=a['unreleased_tag_repair'];new='b'*40
    state={'reference':{'ref':'refs/tags/v5.1.11','object':{'type':'tag','sha':r['original_tag_sha']}},
        'tag':{'sha':r['original_tag_sha'],'tag':'v5.1.11','object':{'type':'commit','sha':r['original_source_commit']}},
        'release':None,'next_release':None,'next_tag':None,'active_runs':[], 'known_external_dependencies':[],
        'old_artifacts':{'total_count':0},'old_run':{'status':'completed','conclusion':'failure','head_sha':r['original_source_commit']},
        'formal_runs':[], 'main':{'sha':new}, 'pr':{'merged':True,'draft':False,'merge_commit_sha':new,'base':{'ref':'main'}},
        'main_runs':[{'head_sha':new,'head_branch':'main','event':'push','status':'completed','conclusion':'success'}],
        'checks':[{'name':n,'status':'completed','conclusion':'success'} for n in ('source-and-tests','docker-installation','windows-toolchain')]}
    return a,state,new


def test_exact_unused_authorized_identity_is_eligible_but_never_mutated():
    a,s,new=sample();before=copy.deepcopy(s);result=validate(s,a,new)
    assert result['eligible'] and result['mutations_performed'] is False and s==before


@pytest.mark.parametrize('failure',['published','draft','v512','next_tag','active','external','artifact','old_delivery',
    'changed_tag','changed_source','changed_main','wrong_pr','not_merged','draft_pr','old_ci','failed_ci','missing_check','skipped_check'])
def test_published_or_used_or_conflicting_or_unverified_tag_is_never_eligible(failure):
    a,s,new=sample()
    if failure=='published':s['release']={'draft':False}
    elif failure=='draft':s['release']={'draft':True}
    elif failure=='v512':s['next_release']={'draft':False}
    elif failure=='next_tag':s['next_tag']={'ref':'refs/tags/v5.1.12'}
    elif failure=='active':s['active_runs']=[{'status':'in_progress'}]
    elif failure=='external':s['known_external_dependencies']=['synthetic consumer']
    elif failure=='artifact':s['old_artifacts']['total_count']=1
    elif failure=='old_delivery':s['formal_runs']=[{'head_branch':'v5.1.11','conclusion':'success'}]
    elif failure=='changed_tag':s['reference']['object']['sha']='c'*40
    elif failure=='changed_source':s['tag']['object']['sha']='c'*40
    elif failure=='changed_main':s['main']['sha']='c'*40
    elif failure=='wrong_pr':s['pr']['merge_commit_sha']='c'*40
    elif failure=='not_merged':s['pr']['merged']=False
    elif failure=='draft_pr':s['pr']['draft']=True
    elif failure=='old_ci':s['main_runs'][0]['head_sha']='c'*40
    elif failure=='failed_ci':s['main_runs'][0]['conclusion']='failure'
    elif failure=='missing_check':s['checks'].pop()
    else:s['checks'][0]['conclusion']='skipped'
    with pytest.raises(ValueError):validate(s,a,new)


@pytest.mark.parametrize('field',['approved','one_time','published_tag_replacement_approved','original_tag_sha','original_source_commit'])
def test_repair_grant_cannot_be_generalized_or_applied_to_published_tags(field):
    a,_,_=sample();a['unreleased_tag_repair'][field]=None
    with pytest.raises(ValueError):validate_authorization(a,'v5.1.11')
