"""Synthetic inline-writing data; uses the disposable suite database/media directory."""
import json,uuid
from sqlalchemy import select,func
from test_content import client,make_type,record_payload as base_record_payload,update_payload,write
from test_archive import upload,image_bytes
from test_api import reset_limiter,csrf,SessionLocal
from app.content_models import RecordBodyMedia,RevisionMediaRef
from app.archive_models import MediaUploadOperation
from app.services.body_media import blocks


def record_payload(t,**kw):return {**base_record_payload(t),**kw}

def block(id,**kw):
    return ':::lj-media-v1\n'+json.dumps(dict(id=id,alt='合成照片',caption='合成说明',width=720,align='center',**kw),ensure_ascii=False)+'\n:::'


def test_media_grammar_samples_and_validation():
    id=str(uuid.uuid4());body=block(id)
    assert len(blocks(body,2))==1 and blocks(body,1)==[]
    for sample in ['```text\n'+body+'\n```','\n'.join('    '+line for line in body.splitlines()),'> '+body.replace('\n','\n> ')]:assert blocks(sample,2)==[]


def test_inline_save_history_guards_409_and_restore(client):
    t=make_type(client);m=upload(client).json();body='# 合成故事\n\n'+block(m['id'])
    r=write(client,'/records',record_payload(t,body=body,body_format=2,status='draft')).json()
    assert r['body']==body and r['body_format']==2
    assert r['connections']['media']==[]  # No duplicate gallery side effect.
    with SessionLocal() as db:
        assert db.get(RecordBodyMedia,(r['id'],m['id']))
        assert db.get(RevisionMediaRef,(r['id'],1,m['id']))
    assert client.get('/api/blog/records/'+r['id']).status_code==404
    denied=write(client,'/records/'+r['id'],update_payload(r,body='changed',body_format=2,expected_revision=999),'put')
    assert denied.status_code==409
    clean=write(client,'/records/'+r['id'],update_payload(r,body='移除当前图片',body_format=2),'put').json()
    assert client.request('DELETE','/api/admin/archive/media/'+m['id'],headers=csrf(client),json={'expected_revision':m['revision']}).status_code==409
    refs=client.get('/api/admin/archive/media/'+m['id']).json()['references'];assert any(x['id']==r['id'] for x in refs)
    restored=client.post(f"/api/admin/recovery/history/{r['id']}/1/restore",headers=csrf(client),json={'expected_revision':clean['revision'],'scope':'content','confirmation':'恢复为新草稿'})
    assert restored.status_code==200,restored.text
    assert restored.json()['body']==body and restored.json()['body_format']==2


def test_unknown_deleted_media_and_bad_attrs_reject_atomically(client):
    t=make_type(client);m=upload(client).json()
    for body in [block(str(uuid.uuid4())),block(m['id']).replace('720','true'),block(m['id']).replace('"center"','"url(javascript:alert(1))"'),block(m['id']).replace('"alt":','"style":"color:red","alt":')]:
        result=write(client,'/records',record_payload(t,body=body,body_format=2));assert result.status_code==422,result.text
    r=write(client,'/records',record_payload(t,body='原样 **Markdown**')).json()
    assert r['body_format']==1 and r['body']=='原样 **Markdown**'
    changed=write(client,'/records/'+r['id'],update_payload(r,title='只改标题'),'put').json()
    assert changed['body_format']==1 and changed['body']==r['body']


def test_upload_same_key_retry_and_conflicting_file(client):
    key=str(uuid.uuid4());headers={**csrf(client),'X-Upload-Key':key}
    def send(data):return client.post('/api/admin/archive/media',headers=headers,files={'file':('synthetic.png',data,'image/png')})
    one=send(image_bytes('PNG'));two=send(image_bytes('PNG'))
    assert one.status_code==200 and two.json()['id']==one.json()['id']
    assert send(image_bytes('JPEG')).status_code==409
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(MediaUploadOperation).where(MediaUploadOperation.request_key==key))==1


def test_upload_process_exit_releases_locks_and_retries_same_identity(client):
    import os,sys,subprocess,base64
    from test_api import PASSWORD
    from app.archive_models import MediaAsset
    key=str(uuid.uuid4());data=image_bytes('PNG')
    code='''import os,sys,json,base64
from fastapi.testclient import TestClient
from app.main import app
from app.services import uploads
args=json.load(sys.stdin)
with TestClient(app,base_url='https://testserver') as c:
 h={'x-csrf-token':c.get('/api/auth/csrf').json()['csrf_token']}
 assert c.post('/api/auth/login',headers=h,json={'username':'test-admin','password':args['password']}).status_code==200
 uploads.os.rename=lambda *a,**kw:os._exit(17)
 c.post('/api/admin/archive/media',headers={**h,'X-Upload-Key':args['key']},files={'file':('synthetic-crash.png',base64.b64decode(args['data']),'image/png')})
'''
    env={**os.environ,'PYTHONPATH':str(__import__('pathlib').Path(__file__).resolve().parents[1]/'backend')}
    result=subprocess.run([sys.executable,'-c',code],input=json.dumps({'password':PASSWORD,'key':key,'data':base64.b64encode(data).decode()}),env=env,text=True,capture_output=True,timeout=30)
    assert result.returncode==17
    with SessionLocal() as db:
        operation=db.scalar(select(MediaUploadOperation).where(MediaUploadOperation.request_key==key));assert operation and operation.state=='pending'
        id=operation.media_id;assert db.get(MediaAsset,id) is None
    retried=client.post('/api/admin/archive/media',headers={**csrf(client),'X-Upload-Key':key},files={'file':('synthetic-crash.png',data,'image/png')})
    assert retried.status_code==200 and retried.json()['id']==id,retried.text
    with SessionLocal() as db:assert db.scalar(select(MediaUploadOperation.state).where(MediaUploadOperation.request_key==key))=='completed'


def test_nested_list_media_is_validated_and_retained_without_rewriting(client):
    t=make_type(client);m=upload(client).json()
    body='- 10月3日\n  - 下午途经山谷\n\n'+'\n'.join('    '+line for line in block(m['id']).splitlines())+'\n\n    返回酒店\n'
    assert blocks(body,2)==[json.loads(block(m['id']).splitlines()[1])]
    response=write(client,'/records',record_payload(t,body=body,body_format=2))
    assert response.status_code==200,response.text
    record=response.json();assert record['body']==body
    with SessionLocal() as db:
        assert db.get(RecordBodyMedia,(record['id'],m['id']))
        assert db.get(RevisionMediaRef,(record['id'],1,m['id']))
    invalid=body.replace(m['id'],str(uuid.uuid4()))
    rejected=write(client,'/records/'+record['id'],update_payload(record,body=invalid),'put')
    assert rejected.status_code==422
    assert client.get('/api/admin/content/records/'+record['id']).json()['body']==body
