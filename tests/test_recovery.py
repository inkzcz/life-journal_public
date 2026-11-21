"""Synthetic recovery and destructive operations run only in the disposable DB."""
import uuid
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_content import client,make_type,field,record_payload,update_payload,write,type_payload
from test_archive import upload,create_record,connect
from test_blog import reader_client,config_put
from test_api import app,login,csrf,SessionLocal,engine,reset_limiter
from app.content_models import ContentRecord,RecordRevision
from app.archive_models import MediaAsset,RecordMedia,Place
from app.recovery_models import MaintenanceJob
from app.services.recovery import cleanup_batch,db_now
A='/api/admin/recovery'

def post(c,path,data):return c.post(A+path,headers=csrf(c),json=data)
def deleted(c,r):
    assert write(c,'/records/'+r['id'],{'expected_revision':r['revision']},'delete').status_code==200
    return c.get(A+'/trash/'+r['id']).json()
def action(c,rows,kind):return post(c,'/trash/'+kind,{'items':[{'id':r['id'],'expected_revision':r['revision']} for r in rows],'confirmation':'恢复' if kind=='restore' else '永久删除'})

def test_trash_restores_structure_and_history_without_copying_shared_media(client):
    t=make_type(client);m=upload(client).json();r1,r2=create_record(client,t),create_record(client,t)
    r1=connect(client,r1,[{'id':m['id'],'cover':True,'caption':'保留照片'}],links=[{'id':r2['id'],'label':'相关'}]).json()
    r2=connect(client,r2,[{'id':m['id']}]).json();d=deleted(client,r1)
    listed=client.get(A+'/trash?q='+d['title']+'&type_id='+t['id']).json();assert d['id'] in [r['id'] for r in listed['items']]
    before_history=client.get(A+'/history/'+r1['id']).json()['total']
    result=action(client,[d],'restore');assert result.status_code==200 and result.json()['items'][0]['state']=='restored'
    current=client.get('/api/admin/content/records/'+r1['id']).json()
    assert current['connections']==d['connections'] and current['body']==d['body'] and current['life']==d['life']
    assert client.get(A+'/history/'+r1['id']).json()['total']==before_history+1
    assert action(client,[d],'restore').json()['items'][0]['state']=='already_active'
    assert client.get('/api/library-media/'+m['id']+'/preview').status_code==200
    assert action(client,[current],'purge').json()['items'][0]['status']==409
    d=deleted(client,current);assert action(client,[d],'purge').json()['items'][0]['state']=='purged'
    assert client.get('/api/admin/content/records/'+r2['id']).json()['connections']['media'][0]['id']==m['id']
    assert client.get('/api/library-media/'+m['id']+'/original').status_code==200
    assert client.get(A+'/history/'+r1['id']).status_code==404


def test_batch_confirmations_revision_conflicts_and_navigation_guard(client):
    t=make_type(client);a,b=[deleted(client,create_record(client,t)) for _ in range(2)]
    bad={**a,'revision':a['revision']-1}
    result=action(client,[bad,b],'restore').json()['items'];assert result[0]['status']==409 and result[1]['state']=='restored'
    assert post(client,'/trash/purge',{'items':[{'id':a['id'],'expected_revision':a['revision']}],'confirmation':'恢复'}).status_code==422
    assert action(client,[a],'restore').json()['items'][0]['state']=='restored'
    a=client.get('/api/admin/content/records/'+a['id']).json()
    assert config_put(client,'navigation',items=[{'id':str(uuid.uuid4()),'kind':'record','name':'旧导航','record_id':a['id']}]).status_code==200
    a=deleted(client,a)
    assert action(client,[a],'purge').json()['items'][0]['status']==409
    assert config_put(client,'navigation',items=[]).status_code==200
    assert action(client,[a],'purge').json()['items'][0]['state']=='purged'
    assert action(client,[a],'purge').json()['items'][0]['state']=='already_purged'

@pytest.mark.parametrize('days',[7,30,90,'never'])
def test_expiry_policies_repeat_safe(client,days):
    t=make_type(client);old=deleted(client,create_record(client,t));fresh=deleted(client,create_record(client,t))
    with SessionLocal() as db:
        row=db.get(ContentRecord,old['id']);row.deleted_at=db_now(db)-timedelta(days=100);row.created_at=row.deleted_at-timedelta(days=1);db.commit()
        result=cleanup_batch(db,days);assert result['removed']==(0 if days=='never' else 1)
        assert cleanup_batch(db,days)['removed']==0
        assert db.get(ContentRecord,fresh['id']) is not None


def test_history_old_schema_new_revision_and_structure_boundary(client):
    t=make_type(client,[field('short_text')]);fid=t['fields'][0]['id']
    r=write(client,'/records',record_payload(t,{fid:'原值'})).json()
    changed=write(client,'/records/'+r['id'],update_payload(r,title='新标题',values={fid:'新值'}),'put').json()
    spec=type_payload(t);spec['fields'][0]['name']='改名';spec['fields'][0]['active']=False
    assert write(client,'/types/'+t['id'],spec,'put').status_code==200
    version=client.get(A+'/history/'+r['id']+'/1').json();assert version['snapshot']['values'][fid]=='原值' and version['can_restore_full']
    restored=post(client,'/history/'+r['id']+'/1/restore',{'expected_revision':changed['revision'],'scope':'full','confirmation':'恢复为新草稿'})
    assert restored.status_code==200,restored.text
    restored=restored.json();assert restored['revision']==3 and restored['values'][fid]=='原值' and restored['status']=='draft' and restored['schema_version']==1
    assert client.get(A+'/history/'+r['id']+'/2').json()['snapshot']['title']=='新标题'
    assert post(client,'/history/'+r['id']+'/1/restore',{'expected_revision':2,'scope':'content','confirmation':'恢复为新草稿'}).status_code==409
    # Simulate a genuine early snapshot; do not claim resource history existed.
    with SessionLocal() as db:
        row=db.get(RecordRevision,(r['id'],1));s=dict(row.snapshot)
        for key in ['connections','life','template']:s.pop(key,None)
        row.snapshot=s;db.commit()
    assert client.get(A+'/history/'+r['id']+'/1').json()['can_restore_full'] is False
    assert post(client,'/history/'+r['id']+'/1/restore',{'expected_revision':3,'scope':'full','confirmation':'恢复为新草稿'}).status_code==422
    assert post(client,'/history/'+r['id']+'/1/restore',{'expected_revision':3,'scope':'content','confirmation':'恢复为新草稿'}).status_code==200


def test_history_missing_shared_link_refuses_full_not_silent_loss(client):
    t=make_type(client);r=create_record(client,t);target=create_record(client,t)
    r=connect(client,r,links=[{'id':target['id'],'label':'旧关联'}]).json();number=r['revision']
    d=deleted(client,target);assert action(client,[d],'purge').json()['items'][0]['state']=='purged'
    r=client.get('/api/admin/content/records/'+r['id']).json()
    response=post(client,f'/history/{r["id"]}/{number}/restore',{'expected_revision':r['revision'],'scope':'full','confirmation':'恢复为新草稿'})
    assert response.status_code==422
    assert client.get('/api/admin/content/records/'+r['id']).json()==r
    assert post(client,f'/history/{r["id"]}/{number}/restore',{'expected_revision':r['revision'],'scope':'content','confirmation':'恢复为新草稿'}).status_code==200


def test_security_and_unconfigured_backup_status(client):
    assert client.get('/api/admin/maintenance/settings').json()['retention_days']==30
    assert client.get('/api/admin/maintenance/settings').json()['keep']==7
    from app.blog_models import SiteConfig
    from sqlalchemy import delete
    with SessionLocal() as db:
        db.execute(delete(SiteConfig).where(SiteConfig.key=='maintenance_status'));db.commit()
    assert client.get('/api/admin/maintenance/status').json()['online'] is False
    assert client.get('/api/admin/maintenance/status').json()['configured'] is False
    assert client.post('/api/admin/maintenance/jobs',headers=csrf(client),json={'kind':'backup','confirmation':'执行备份'}).status_code==503
    with SessionLocal() as db:
        db.add(SiteConfig(id=str(uuid.uuid4()),key='maintenance_status',value={'heartbeat':db_now(db).isoformat(),'configured':False},revision=1));db.commit()
    blocked=client.post('/api/admin/maintenance/jobs',headers=csrf(client),json={'kind':'backup','confirmation':'执行备份'})
    assert blocked.status_code==409 and '目录' in blocked.json()['detail']
    with reader_client(client.app) as reader:
        for path in [A+'/trash',A+'/media','/api/admin/maintenance/settings','/api/admin/maintenance/backups']:
            assert reader.get(path).status_code==403
    with TestClient(app,base_url='https://testserver') as off:
        login(off);assert off.get(A+'/trash').status_code==200
        assert off.get('/api/journals').status_code==200
    assert client.post(A+'/trash/restore',json={}).status_code==403

def test_batch_restore_and_media_index_recovery(client):
    t=make_type(client);rows=[deleted(client,create_record(client,t)) for _ in range(2)]
    assert [x['state'] for x in action(client,rows,'restore').json()['items']]==['restored','restored']
    m=upload(client).json()
    response=client.request('DELETE','/api/admin/archive/media/'+m['id'],headers=csrf(client),json={'expected_revision':m['revision']});assert response.status_code==200
    trashed=next(x for x in client.get(A+'/media').json() if x['id']==m['id'])
    assert post(client,'/media/'+m['id']+'/restore',{'expected_revision':trashed['revision']}).status_code==200
    assert client.get('/api/library-media/'+m['id']+'/preview').status_code==200


def test_concurrent_restore_vs_purge_does_not_delete_active_record(client):
    from concurrent.futures import ThreadPoolExecutor
    t=make_type(client);d=deleted(client,create_record(client,t))
    def run(kind):
        with TestClient(client.app,base_url='https://testserver') as other:
            login(other);return action(other,[d],kind).json()['items'][0]
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,['restore','purge']))
    assert sum(r['state'] in {'restored','purged'} for r in results)==1
    with SessionLocal() as db:
        r=db.get(ContentRecord,d['id'])
        if r:assert r.deleted_at is None


def test_cleanup_page_cursor_does_not_starve_after_protected_record(client):
    from app.blog_models import NavigationItem
    from datetime import date
    t=make_type(client)
    with SessionLocal() as db:
        for i in range(55):
            r=ContentRecord(id=str(uuid.uuid4()),type_id=t['id'],schema_version=1,title='虚构批次',display_date=date(2026,1,1),deleted_at=db_now(db)-timedelta(days=200+i),created_at=db_now(db)-timedelta(days=300+i))
            db.add(r);db.flush()
            if i==54:db.add(NavigationItem(id=str(uuid.uuid4()),name='受保护导航',kind='record',record_id=r.id,position=0))
        db.commit();one=cleanup_batch(db,30,limit=50);two=cleanup_batch(db,30,limit=5,after=one['cursor'])
        assert one['removed']==49 and len(one['errors'])==1 and two['removed']==5


def test_history_restores_inactive_template_pinned_version(client):
    from test_templates import create,record,edit,save
    t=create(client);r=record(client,t);fid=t['fields'][0]['key']
    payload=edit(t);payload['fields'][0]['field']['name']='新名称';t2=save(client,payload,t['id']).json()
    changed=write(client,'/records/'+r['id'],update_payload(r,schema_version=t2['schema_version'],template={'id':t2['id'],'version':t2['version']},title='新版记录'),'put').json()
    assert save(client,edit(t2,active=False),t2['id']).status_code==200
    response=post(client,f'/history/{r["id"]}/1/restore',{'expected_revision':changed['revision'],'scope':'full','confirmation':'恢复为新草稿'})
    assert response.status_code==200,response.text
    assert response.json()['template']['version']==1 and response.json()['schema_version']==1
    assert response.json()['values'][fid]==r['values'][fid] and response.json()['recovery_warnings']


def test_backup_settings_remain_available_to_admin_with_blog_disabled():
    from app.services.blog import save_config
    from app.services.maintenance import settings_data
    with SessionLocal() as db:
        current=settings_data(db);save_config(db,'recovery',{k:v for k,v in current.items() if k!='revision'}|{'cleanup_confirmed':False},current['revision']);db.commit()
    with TestClient(app,base_url='https://testserver') as off:
        login(off)
        assert off.get('/api/admin/maintenance/settings').status_code==200
        assert off.post('/api/admin/maintenance/jobs',headers=csrf(off),json={'kind':'cleanup','confirmation':'永久清理','expected_settings_revision':0}).status_code==409
        assert off.get('/api/admin/recovery/trash').status_code==200


def test_first_start_requires_explicit_policy_confirmation_and_rechecks_queued_job(client,monkeypatch):
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL scheduler leadership')
    from app.services.blog import save_config
    from app.services.maintenance import settings_data,enqueue
    from app.maintenance_worker import leader_loop,run_job
    from app.blog_models import SiteConfig
    from sqlalchemy import delete,func
    monkeypatch.setenv('DYNAMIC_BLOG_ENABLED','true')
    with SessionLocal() as db:
        db.execute(delete(MaintenanceJob));db.execute(delete(SiteConfig).where(SiteConfig.key.in_(['recovery','maintenance_status'])));db.commit()
    t=make_type(client);r=deleted(client,create_record(client,t))
    with SessionLocal() as db:
        row=db.get(ContentRecord,r['id']);row.deleted_at=db_now(db)-timedelta(days=200);row.created_at=row.deleted_at-timedelta(days=1);db.commit()
    leader_loop(once=True)
    with SessionLocal() as db:
        assert db.get(ContentRecord,r['id']) is not None
        assert not db.scalar(select(func.count()).select_from(MaintenanceJob).where(MaintenanceJob.kind=='cleanup'))
    cfg=client.get('/api/admin/maintenance/settings').json();assert cfg['retention_days']==30 and cfg['cleanup_confirmed'] is False
    blocked=client.post('/api/admin/maintenance/jobs',headers=csrf(client),json={'kind':'cleanup','confirmation':'永久清理','expected_settings_revision':cfg['revision']})
    assert blocked.status_code==409 and '确认清理策略' in blocked.json()['detail']
    payload={k:v for k,v in cfg.items() if k!='revision'};payload.update(cleanup_confirmed=True,cleanup_reviewed=True,expected_revision=cfg['revision'])
    assert client.put('/api/admin/maintenance/settings',headers=csrf(client),json=payload).status_code==200
    with SessionLocal() as db:
        job=enqueue(db,'cleanup');db.commit();id=job.id
        config=settings_data(db);rev=config.pop('revision');config['cleanup_confirmed']=False;save_config(db,'recovery',config,rev);db.commit()
    run_job(id)
    with SessionLocal() as db:
        assert db.get(ContentRecord,r['id']) is not None and db.get(MaintenanceJob,id).state=='failed'


def test_cleanup_skips_impossible_deletion_timestamps_and_active_records(client):
    t=make_type(client);bad=deleted(client,create_record(client,t));active=create_record(client,t)
    with SessionLocal() as db:
        row=db.get(ContentRecord,bad['id']);row.deleted_at=db_now(db)-timedelta(days=365)  # older than creation
        db.commit();cleanup_batch(db,30)
        assert db.get(ContentRecord,bad['id']) is not None and db.get(ContentRecord,active['id']) is not None


def test_policy_change_between_cleanup_batches_stops_remaining_work(client,monkeypatch):
    monkeypatch.setenv('DYNAMIC_BLOG_ENABLED','true')
    import app.maintenance_worker as worker
    from app.services.maintenance import settings_data,enqueue
    from app.services.blog import save_config
    from datetime import date
    t=make_type(client)
    with SessionLocal() as db:
        config=settings_data(db);rev=config.pop('revision');config['cleanup_confirmed']=True;save_config(db,'recovery',config,rev)
        from app.services.maintenance import mark_cleanup_review
        mark_cleanup_review(db,True)
        for _ in range(60):
            db.add(ContentRecord(id=str(uuid.uuid4()),type_id=t['id'],schema_version=1,title='虚构分批策略',display_date=date(2026,1,1),created_at=db_now(db)-timedelta(days=10001),deleted_at=db_now(db)-timedelta(days=10000)))
        db.commit();job=enqueue(db,'cleanup');db.commit();id=job.id
    original=worker.cleanup_batch;called=[]
    def changed(*a,**k):
        result=original(*a,**k);called.append(result)
        with SessionLocal() as db:
            config=settings_data(db);rev=config.pop('revision');config['cleanup_confirmed']=False;save_config(db,'recovery',config,rev);db.commit()
        return result
    monkeypatch.setattr(worker,'cleanup_batch',changed);worker.run_job(id)
    with SessionLocal() as db:
        assert len(called)==1 and db.get(MaintenanceJob,id).state=='partial'
        assert db.get(MaintenanceJob,id).result['removed']==50
        assert len(list(db.scalars(select(ContentRecord).where(ContentRecord.type_id==t['id']))))==10


def test_legacy_confirmation_and_disabled_flag_do_not_resume_cleanup(client,monkeypatch):
    from app.services.blog import save_config
    from app.services.maintenance import settings_data
    from app.blog_models import SiteConfig
    from sqlalchemy import delete
    from app.maintenance_worker import leader_loop
    monkeypatch.setenv('DYNAMIC_BLOG_ENABLED','false')
    with SessionLocal() as db:
        db.execute(delete(MaintenanceJob))
        db.execute(delete(SiteConfig).where(SiteConfig.key.in_(['cleanup_consent','maintenance_status'])))
        config=settings_data(db);rev=config.pop('revision')
        save_config(db,'recovery',{**config,'cleanup_confirmed':True},rev);db.commit()
    t=make_type(client);r=deleted(client,create_record(client,t))
    with SessionLocal() as db:
        row=db.get(ContentRecord,r['id']);row.deleted_at=db_now(db)-timedelta(days=200);row.created_at=row.deleted_at-timedelta(days=1);db.commit()
    if engine.dialect.name=='postgresql':leader_loop(once=True)
    else:
        with pytest.raises(RuntimeError,match='仅支持 PostgreSQL'):leader_loop(once=True)
    with SessionLocal() as db:
        assert db.get(ContentRecord,r['id']) is not None
        stored=db.scalar(select(SiteConfig).where(SiteConfig.key=='recovery'))
        assert stored.value['cleanup_confirmed'] is True  # original config preserved
        assert settings_data(db)['cleanup_confirmed'] is False
    cfg=client.get('/api/admin/maintenance/settings').json()
    payload={**{k:v for k,v in cfg.items() if k!='revision'},'cleanup_confirmed':True,'expected_revision':cfg['revision']}
    assert client.put('/api/admin/maintenance/settings',headers=csrf(client),json=payload).status_code==422
    assert client.put('/api/admin/maintenance/settings',headers=csrf(client),json={**payload,'cleanup_reviewed':True}).status_code==200
    with SessionLocal() as db:assert settings_data(db)['cleanup_confirmed'] is True
