import uuid
from test_content import client,make_type,record_payload,write,update_payload
from test_archive import upload
from test_api import reset_limiter,csrf
A='/api/admin/archive'
def folder(c,name='合成目录',parent=None):
    r=c.post(A+'/folders',headers=csrf(c),json={'name':name+uuid.uuid4().hex[:6],'parent_id':parent});assert r.status_code==200,r.text;return r.json()
def batch(c,assets,action,**kw):
    return c.post(A+'/media-batch',headers=csrf(c),json={'items':[{'id':a['id'],'expected_revision':a['revision']} for a in assets],'action':action,'confirmation':'执行批量操作',**kw})
def test_tree_cycles_conflicts_depth_and_safe_delete(client):
    f=folder(client);g=folder(client,parent=f['id'])
    assert client.put(A+'/folders/'+f['id'],headers=csrf(client),json={'name':f['name'],'parent_id':g['id'],'expected_revision':1}).status_code==422
    assert client.request('DELETE',A+'/folders/'+f['id'],headers=csrf(client),json={'expected_revision':1}).status_code==409
    assert client.post(A+'/folders',headers=csrf(client),json={'name':f['name'].upper()}).status_code==409
    for _ in range(6):g=folder(client,parent=g['id'])
    assert client.post(A+'/folders',headers=csrf(client),json={'name':'第九层','parent_id':g['id']}).status_code==422

def test_move_category_trash_keep_uuid_bytes_and_nonempty_folder(client):
    f=folder(client);a=upload(client).json();old=client.get('/api/library-media/'+a['id']+'/preview').content
    moved=batch(client,[a],'move',folder_id=f['id']);assert moved.status_code==200,moved.text;a=moved.json()['items'][0]
    assert a['folder_id']==f['id']
    assert client.get(A+'/media',params={'folder_id':f['id']}).json()['items'][0]['id']==a['id']
    assert client.get('/api/library-media/'+a['id']+'/preview').content==old
    changed=batch(client,[a],'category',category='合成旅行');assert changed.status_code==200;a=changed.json()['items'][0];assert a['category']=='合成旅行'
    assert batch(client,[a],'trash').status_code==200
    assert client.request('DELETE',A+'/folders/'+f['id'],headers=csrf(client),json={'expected_revision':1}).status_code==409

def test_batch_rejects_partial_mutation_and_stale_revision(client):
    a,b=upload(client).json(),upload(client).json();t=make_type(client)
    r=write(client,'/records',{**record_payload(t),'connections':{'media':[{'id':b['id'],'cover':True}],'places':[],'links':[]}});assert r.status_code==200
    result=batch(client,[a,b],'trash');assert result.status_code==409
    assert client.get('/api/library-media/'+a['id']+'/preview').status_code==200
    assert batch(client,[{**a,'revision':999}],'move').status_code==409
    assert client.post(A+'/media-batch',json={'action':'trash'}).status_code==403

def test_connection_details_batch_load_folder_metadata_without_n_plus_one(client):
    from sqlalchemy import event
    from test_api import engine,SessionLocal
    from app.services.archive import connections_data
    t=make_type(client);images=[upload(client).json() for _ in range(3)]
    def record(media):
        response=write(client,'/records',{**record_payload(t),'connections':{'media':[{'id':m['id']} for m in media],'links':[],'places':[]}});assert response.status_code==200,response.text;return response.json()['id']
    one,many=record(images[:1]),record(images)
    def count(id):
        queries=[]
        def capture(*args):queries.append(1)
        event.listen(engine,'before_cursor_execute',capture)
        try:
            with SessionLocal() as db:result=connections_data(db,id)
        finally:event.remove(engine,'before_cursor_execute',capture)
        assert all(x['asset']['folder_id'] is None for x in result['media'])
        return len(queries)
    assert count(one)==count(many)==4
