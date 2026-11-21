import uuid
from test_content import client,make_type,record_payload,write
from test_api import reset_limiter,csrf,SessionLocal
from app.archive_models import Place,PlaceAlias
from app.content_models import RecordRevision
A='/api/admin/archive/places'
def place(c):
    result=c.post(A,headers=csrf(c),json={'name':'合成重复地点','city':'合成城市'});assert result.status_code==200,result.text;return result.json()
def test_unused_delete_and_current_history_block(client):
    p=place(client);r=client.request('DELETE',A+'/'+p['id'],headers=csrf(client),json={'expected_revision':p['revision']});assert r.status_code==200,r.text
    p=place(client);t=make_type(client);r=write(client,'/records',{**record_payload(t),'connections':{'media':[],'links':[],'places':[p['id']]}}).json()
    denied=client.request('DELETE',A+'/'+p['id'],headers=csrf(client),json={'expected_revision':p['revision']});assert denied.status_code==409
    usage=client.get(A+'/'+p['id']).json()['usages'];assert any(x['kind']=='历史修订' for x in usage)

def test_merge_preserves_immutable_history_and_requires_restore_confirmation(client):
    p,q=place(client),place(client);t=make_type(client)
    r=write(client,'/records',{**record_payload(t),'connections':{'media':[],'links':[],'places':[p['id'],q['id']]}}).json()
    with SessionLocal() as db:before=db.get(RecordRevision,(r['id'],1)).snapshot
    candidates=client.get(A+'/'+p['id']+'/duplicates').json();assert q['id'] in [x['id'] for x in candidates]
    result=client.post(A+'/'+p['id']+'/merge',headers=csrf(client),json={'target_id':q['id'],'expected_revision':p['revision'],'target_revision':q['revision'],'confirmation':'合并地点'});assert result.status_code==200,result.text
    now=client.get('/api/admin/content/records/'+r['id']).json();assert [x['id'] for x in now['connections']['places']]==[q['id']] and now['revision']==2
    with SessionLocal() as db:
        assert db.get(RecordRevision,(r['id'],1)).snapshot==before
        assert not db.get(Place,p['id']).active and db.get(PlaceAlias,p['id']).target_id==q['id']
    payload={'expected_revision':now['revision'],'scope':'full','confirmation':'恢复为新草稿'}
    url='/api/admin/recovery/history/'+r['id']+'/1/restore'
    assert client.post(url,headers=csrf(client),json=payload).status_code==409
    restored=client.post(url,headers=csrf(client),json={**payload,'resolve_place_aliases':True});assert restored.status_code==200,restored.text
    assert [x['id'] for x in restored.json()['connections']['places']]==[q['id']]
    assert client.request('DELETE',A+'/'+p['id'],headers=csrf(client),json={'expected_revision':2}).status_code==409
    assert client.post(A+'/'+q['id']+'/merge',headers=csrf(client),json={'target_id':p['id'],'expected_revision':2,'target_revision':2,'confirmation':'合并地点'}).status_code==409

def test_place_delete_requires_fresh_revision_and_no_history(client):
    p=place(client)
    assert client.request('DELETE',A+'/'+p['id'],headers=csrf(client),json={'expected_revision':99}).status_code==409
    assert client.get(A+'/'+p['id']).status_code==200
    assert client.request('DELETE',A+'/'+p['id'],json={'expected_revision':1}).status_code==403
