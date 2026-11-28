import copy
import pytest
from scripts.release_artifact_cleanup import validate_artifact

def sample():
    version='v5.1.11';revision='a'*40;name='life-journal-delivery-'+version+'-'+revision
    return {'id':123,'name':name,'expired':False,'workflow_run':{'id':456,'head_sha':revision}},dict(artifact_id=123,run_id=456,name=name,version=version,revision=revision)

def test_exact_current_formal_artifact_can_be_selected():
    m,args=sample();validate_artifact(m,**args)

@pytest.mark.parametrize('key,value',[('id',999),('name','another-run'),('expired',True),('workflow_run',{'id':457,'head_sha':'a'*40}),('workflow_run',{'id':456,'head_sha':'b'*40})])
def test_other_run_or_name_is_rejected(key,value):
    m,args=sample();m[key]=value
    with pytest.raises(ValueError,match='nothing deleted'):validate_artifact(m,**args)

@pytest.mark.parametrize('field,value',[('artifact_id',0),('run_id',True),('version','v5.1.10'),('revision','main'),('name','life-journal-delivery-latest')])
def test_unsafe_selection_is_rejected(field,value):
    m,args=sample();args[field]=value
    with pytest.raises(ValueError):validate_artifact(m,**args)


def test_new_512_cleanup_retains_run_and_exact_artifact_identity_guards():
    version='v5.1.12';revision='a'*40;name='life-journal-delivery-'+version+'-'+revision
    metadata={'id':123,'name':name,'expired':False,'workflow_run':{'id':456,'head_sha':revision}}
    from scripts.release_artifact_cleanup import validate_artifact
    validate_artifact(metadata,artifact_id=123,run_id=456,name=name,version=version,revision=revision)
    for key,value in [('version','v5.1.13'),('run_id',457),('name',name+'-other'),('revision','b'*40)]:
        values={'artifact_id':123,'run_id':456,'name':name,'version':version,'revision':revision};values[key]=value
        with pytest.raises(ValueError):validate_artifact(metadata,**values)
