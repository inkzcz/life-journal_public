import uuid,os,sys,json,subprocess
import pytest
from sqlalchemy import select
from test_content import client,make_type,record_payload,write
from test_archive import upload
from test_api import reset_limiter,csrf,SessionLocal,PASSWORD
from app.archive_models import MediaAsset,MediaPurgeOperation
A='/api/admin/archive'
def trash(c,m):
    r=c.request('DELETE',A+'/media/'+m['id'],headers=csrf(c),json={'expected_revision':m['revision']});assert r.status_code==200,r.text
    return c.get(A+'/media-trash/'+m['id']).json()
def action(c,rows,mode,key=None):
    r=c.post(A+'/media-trash/actions',headers=csrf(c),json={'action':mode,'request_key':key or str(uuid.uuid4()),'confirmation':'永久删除图片' if mode=='purge' else '恢复图片','confirm_count':len(rows),'items':[{'id':m['id'],'expected_revision':m['revision']} for m in rows]});assert r.status_code==200,r.text;return r.json()['items']

def test_restore_then_purge_idempotency_and_files(client):
    m=upload(client).json();m=trash(client,m)
    assert client.get('/api/library-media/'+m['id']+'/preview').status_code==404
    assert client.get(A+'/media-trash/'+m['id']+'/preview').status_code==200
    assert action(client,[m],'restore')[0]['state']=='restored'
    m=client.get(A+'/media/'+m['id']).json();m=trash(client,m);key=str(uuid.uuid4())
    result=action(client,[m],'purge',key)[0];assert result['state']=='completed',result
    assert action(client,[m],'purge',key)[0]['state']=='completed'
    assert not (client.app.state.settings.media_dir/'library-v1'/m['id']).exists()
    with SessionLocal() as db:assert db.get(MediaAsset,m['id']) is None

def test_all_history_and_markdown_field_references_block_trash(client):
    m=upload(client).json();t=make_type(client)
    r=write(client,'/records',{**record_payload(t),'body':'![合成](/api/library-media/'+m['id']+'/preview)'});assert r.status_code==200,r.text
    denied=client.request('DELETE',A+'/media/'+m['id'],headers=csrf(client),json={'expected_revision':m['revision']});assert denied.status_code==409
    usage=client.get(A+'/media/'+m['id']).json()['usages'];assert any(x['kind']=='历史修订' for x in usage)
    assert client.post(A+'/media-trash/actions',json={}).status_code==403

def test_partial_batch_and_unknown_file_refuse_deletion(client):
    a,b=trash(client,upload(client).json()),trash(client,upload(client).json())
    extra=client.app.state.settings.media_dir/'library-v1'/b['id']/'unknown.bin';extra.write_bytes(b'synthetic retained')
    result=action(client,[a,b],'purge');assert result[0]['state']=='completed' and result[1]['state']=='blocked'
    assert extra.read_bytes()==b'synthetic retained'
    extra.unlink()  # remove only the deliberately injected test artifact after the refusal assertion

@pytest.mark.parametrize('stage',['prepared','after_rename','isolated','db_committed','after_unlink','files_removed'])
def test_real_process_exit_delete_retry_and_cancel(client,stage):
    m=trash(client,upload(client).json());key=str(uuid.uuid4())
    code='''import sys,json,os,signal
from fastapi.testclient import TestClient
from app.main import app
from app.services import media_recovery as service
args=json.load(sys.stdin)
service.checkpoint=lambda stage:os.kill(os.getpid(),signal.SIGKILL) if stage==args['stage'] else None
with TestClient(app,base_url='https://testserver') as c:
 h={'x-csrf-token':c.get('/api/auth/csrf').json()['csrf_token']}
 assert c.post('/api/auth/login',headers=h,json={'username':'test-admin','password':args['password']}).status_code==200
 c.post('/api/admin/archive/media-trash/actions',headers=h,json={'action':'purge','request_key':args['key'],'confirmation':'永久删除图片','confirm_count':1,'items':[{'id':args['id'],'expected_revision':args['revision']}]})
'''
    env={**os.environ,'PYTHONPATH':str(__import__('pathlib').Path(__file__).parents[1]/'backend')}
    r=subprocess.run([sys.executable,'-c',code],env=env,input=json.dumps({'password':PASSWORD,'stage':stage,'id':m['id'],'revision':m['revision'],'key':key}),capture_output=True,text=True,timeout=30)
    assert r.returncode==-9,r.stderr[-300:]
    with SessionLocal() as db:op=db.scalar(select(MediaPurgeOperation).where(MediaPurgeOperation.media_id==m['id']));opid=op.id;assert op.state!='completed'
    from app.services.media_recovery import validate_backup_media
    with SessionLocal() as db:validate_backup_media(db,client.app.state.settings.media_dir)
    if stage in ['prepared','after_rename','isolated']:
        response=client.post(A+'/media-purge-operations/'+opid,headers=csrf(client),json={'action':'cancel','confirmation':'取消删除'});assert response.status_code==200,response.text
        assert (client.app.state.settings.media_dir/'library-v1'/m['id']/'original').is_file()
        refreshed=client.get(A+'/media-trash/'+m['id']).json();assert not refreshed['purge_operation_id']
        assert action(client,[refreshed],'restore')[0]['state']=='restored'
    else:
        assert client.post(A+'/media-purge-operations/'+opid,headers=csrf(client),json={'action':'cancel','confirmation':'取消删除'}).status_code==409
        response=client.post(A+'/media-purge-operations/'+opid,headers=csrf(client),json={'action':'retry','confirmation':'继续永久删除'});assert response.status_code==200,response.text
        assert response.json()['state']=='completed'

def test_real_process_mutex_and_backup_barrier(client):
    from pathlib import Path
    from app.db import engine
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL session advisory lock')
    from app.services.media_recovery import operation_lock
    from app.services.write_barrier import frozen
    from fastapi import HTTPException
    code='''import sys
from app.db import SessionLocal
from app.services.media_recovery import operation_lock
with SessionLocal() as db,operation_lock(db):
 print('locked',flush=True)
 sys.stdin.readline()
'''
    env={**os.environ,'PYTHONPATH':str(Path(__file__).parents[1]/'backend')}
    p=subprocess.Popen([sys.executable,'-c',code],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    import select as io_select
    try:
        assert io_select.select([p.stdout],[],[],10)[0],'lock child timeout'
        assert p.stdout.readline().strip()=='locked'
        with SessionLocal() as db,pytest.raises(HTTPException) as exc:
            with operation_lock(db):pass
        assert exc.value.status_code==409
        p.kill();p.wait(timeout=5)
        with SessionLocal() as db,operation_lock(db):pass  # crash releases session lock
        with frozen(engine),SessionLocal() as db,pytest.raises(HTTPException) as exc:
            with operation_lock(db):pass
        assert exc.value.status_code==503
    finally:
        if p.poll() is None:p.kill();p.wait(timeout=5)

def test_reference_audit_fail_closed(client):
    from app.archive_models import ResourceReferenceAudit
    m=trash(client,upload(client).json())
    with SessionLocal() as db:
        row=db.get(ResourceReferenceAudit,'media');original=row.value
        row.value={'media_version':1,'issues':[{'code':'unknown_snapshot'}]};db.commit()
    try:
        result=action(client,[m],'purge')[0];assert result['state']=='blocked'
        assert (client.app.state.settings.media_dir/'library-v1'/m['id']/'original').is_file()
    finally:
        with SessionLocal() as db:db.get(ResourceReferenceAudit,'media').value=original;db.commit()

def test_batch_restore_reports_each_item_and_keeps_original_bytes(client):
    a,b=trash(client,upload(client).json()),trash(client,upload(client).json())
    missing={'id':str(uuid.uuid4()),'revision':1}
    result=action(client,[a,b,missing],'restore')
    assert [r['state'] for r in result]==['restored','restored','blocked']
    for m in [a,b]:assert client.get('/api/library-media/'+m['id']+'/original').status_code==200

def test_trash_with_legacy_history_reference_cannot_be_permanently_deleted(client):
    from app.models import now
    m=upload(client).json();t=make_type(client)
    response=write(client,'/records',{**record_payload(t),'connections':{'media':[{'id':m['id']}],'places':[],'links':[]}});assert response.status_code==200,response.text
    # Simulate a historical soft-delete predating today's stricter trash check.
    with SessionLocal() as db:row=db.get(MediaAsset,m['id']);row.deleted_at=now();row.revision+=1;db.commit()
    deleted=client.get(A+'/media-trash/'+m['id']).json();result=action(client,[deleted],'purge')[0]
    assert result['state']=='blocked' and result['reason']['references']
    assert (client.app.state.settings.media_dir/'library-v1'/m['id']/'original').is_file()

def test_real_purge_process_blocks_second_purge_restore_and_backup(client):
    from pathlib import Path
    from app.db import engine
    from sqlalchemy import text
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL process/barrier integration')
    m=trash(client,upload(client).json())
    code='''import sys,json,uuid
from app.db import SessionLocal
from app.models import User
from app.services import media_recovery as service
from sqlalchemy import select
args=json.loads(sys.stdin.readline())
def pause(stage):
 if stage=='prepared':
  print('prepared',flush=True)
  sys.stdin.readline()
service.checkpoint=pause
with SessionLocal() as db:
 actor=db.scalar(select(User).where(User.username=='test-admin'))
 service.purge_media(db,args['id'],args['revision'],actor.id,str(uuid.uuid4()),args['root'])
'''
    env={**os.environ,'PYTHONPATH':str(Path(__file__).parents[1]/'backend')}
    p=subprocess.Popen([sys.executable,'-c',code],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    import select as io_select
    try:
        p.stdin.write(json.dumps({'id':m['id'],'revision':m['revision'],'root':str(client.app.state.settings.media_dir)})+'\n');p.stdin.flush()
        assert io_select.select([p.stdout],[],[],10)[0] and p.stdout.readline().strip()=='prepared'
        assert action(client,[m],'purge')[0]['state']=='blocked'
        assert action(client,[m],'restore')[0]['state']=='blocked'
        with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as con:
            got=con.scalar(text('SELECT pg_try_advisory_lock(721934003)'))
            if got:con.scalar(text('SELECT pg_advisory_unlock(721934003)'))
            assert not got,'backup must not pass a live file-operation writer barrier'
    finally:
        if p.poll() is None:p.kill()
        p.wait(timeout=5)
    op=next(o for o in client.get(A+'/media-purge-operations').json() if o['media_id']==m['id'])
    r=client.post(A+'/media-purge-operations/'+op['id'],headers=csrf(client),json={'action':'cancel','confirmation':'取消删除'});assert r.status_code==200,r.text
