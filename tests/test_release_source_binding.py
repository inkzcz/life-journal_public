"""Normal corrective source binding never edits the original grant or any tag."""
import copy,hashlib,json
from pathlib import Path
import pytest
from scripts.release_authorization import read_authorization,validate_authorization

ROOT=Path(__file__).resolve().parents[1]
ORIGINAL='licensing/BINARY_RELEASE_v5.1.12_AUTHORIZATION.json'
SUPPLEMENT='licensing/BINARY_RELEASE_v5.1.12_SOURCE_BINDING_AUTHORIZATION.json'
ORIGINAL_SHA='515baf83a861c1804c82b9ae94370dba7a0e689aadf24907fec452ef6bdfca06'


def test_original_registration_is_immutable_and_supplement_uses_same_normal_grant():
    original=(ROOT/ORIGINAL).read_bytes();assert hashlib.sha256(original).hexdigest()==ORIGINAL_SHA
    historical=json.loads(original);current=read_authorization(ROOT,'v5.1.12')
    assert historical['source_pull_request']==10 and current['source_pull_request']==11
    assert current['version']==historical['version']=='v5.1.12'
    assert current['previous_authorization']==ORIGINAL and current['previous_authorization_sha256']==ORIGINAL_SHA
    assert current['technically_reviewed_workflows']==historical['technically_reviewed_workflows']
    assert current['required_conditions']==historical['required_conditions']
    with pytest.raises(ValueError):validate_authorization(historical,'v5.1.12')


@pytest.mark.parametrize('field,value',[('source_pull_request',10),('version','v5.1.13'),('previous_authorization','../other.json'),('previous_authorization_sha256','a'*64),('registry_push_approved',True),('nas_access_approved',True),('private_repository_changes_approved',True),('binary_publication_approved',False),('owner_confirmation_reference',''),('reviewed_main_baseline','a'*40),('reviewed_feature_head','main'),('unreleased_tag_repair',{}),('retained_tag_identity',{}),('source_binding_supplement',None),('source_binding_supplement',[])])
def test_source_supplement_cannot_expand_or_repair_the_grant(field,value):
    current=read_authorization(ROOT,'v5.1.12');current[field]=value
    with pytest.raises(ValueError):validate_authorization(current,'v5.1.12')


@pytest.mark.parametrize('field,value',[('scope','tag-repair'),('previous_source_pull_request',9),('previous_merge_commit','a'*40),('tag_repair_approved',True),('historical_tag_replacement_approved',True)])
def test_source_binding_ancestry_is_exact_and_never_a_tag_repair(field,value):
    current=copy.deepcopy(read_authorization(ROOT,'v5.1.12'));current['source_binding_supplement'][field]=value
    with pytest.raises(ValueError):validate_authorization(current,'v5.1.12')


def test_read_checks_the_original_bytes_before_accepting_current_source_binding(tmp_path):
    (tmp_path/'licensing').mkdir()
    for name in (ORIGINAL,SUPPLEMENT):(tmp_path/name).write_bytes((ROOT/name).read_bytes())
    assert read_authorization(tmp_path,'v5.1.12')['source_pull_request']==11
    (tmp_path/ORIGINAL).write_bytes((ROOT/ORIGINAL).read_bytes()+b'\n')
    with pytest.raises(ValueError,match='remain unchanged'):read_authorization(tmp_path,'v5.1.12')


@pytest.mark.parametrize('name',[ORIGINAL,SUPPLEMENT])
def test_original_and_supplement_cannot_be_replaced_with_symlinks(tmp_path,name):
    (tmp_path/'licensing').mkdir()
    for item in (ORIGINAL,SUPPLEMENT):(tmp_path/item).write_bytes((ROOT/item).read_bytes())
    target=tmp_path/'synthetic-authorization.json';target.write_bytes((ROOT/name).read_bytes())
    (tmp_path/name).unlink();(tmp_path/name).symlink_to(target)
    with pytest.raises(ValueError):read_authorization(tmp_path,'v5.1.12')
