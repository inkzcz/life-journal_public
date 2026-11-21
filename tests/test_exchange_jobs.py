"""Real API + files + DB: preview, atomic drafts, exact photo reuse and retries."""
import io,json,uuid,zipfile
from pathlib import Path
import pytest
from sqlalchemy import select,func
from test_content import client,make_type
from test_api import reset_limiter,csrf,SessionLocal,MEDIA_DIR
from app.content_models import ContentRecord,RecordRevision
from app.archive_models import MediaAsset,Place
from app.exchange.models import ExchangeJob,ExchangeFileOperation
from app.exchange import jobs


def packet(t):
    p=Path(__file__).resolve().parents[1]/'docs/v5.1.5/examples/travel-with-photos.zip'
    with zipfile.ZipFile(p) as z:files={n:z.read(n) for n in z.namelist()}
    value=json.loads(files['travel.json']);value['records'][0]['type_slug']=t['slug'];value['records'][0]['title']='导入验收-'+t['slug'];files['travel.json']=json.dumps(value).encode()
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        for n,data in files.items():z.writestr(n,data)
    return b.getvalue(),files

def prepare(c,t,key=None):
    raw,files=packet(t);r=c.post('/api/admin/exchange/preview',headers=csrf(c)|{'X-Import-Key':key or str(uuid.uuid4())},files={'file':('trip.zip',raw)})
    assert r.status_code==200,r.text
    return r.json(),raw,files

def confirm(c,row):return c.post('/api/admin/exchange/jobs/'+row['id']+'/confirm',json={'expected_revision':row['revision'],'confirmation':'创建草稿'},headers=csrf(c))

def test_real_package_is_previewed_then_imported_once_as_draft(client):
    t=make_type(client);key=str(uuid.uuid4())
    with SessionLocal() as db:media_before=db.scalar(select(func.count()).select_from(MediaAsset))
    row,raw,files=prepare(client,t,key)
    assert row['valid'] and len(row['images'])==2
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ContentRecord).where(ContentRecord.type_id==t['id']))==0
        assert db.scalar(select(func.count()).select_from(MediaAsset))==media_before
    assert client.get(row['images'][0]['url']).status_code==200
    first=confirm(client,row);assert first.status_code==200,first.text;done=first.json()
    second=confirm(client,row);assert second.status_code==200 and second.json()['replayed']
    assert second.json()['result_ids']==done['result_ids'] and len(done['result_ids'])==1
    record=client.get('/api/admin/content/records/'+done['result_ids'][0]).json()
    assert record['status']=='draft' and record['display_date']=='2026-11-05' and record['life']['start_date']=='2026-10-01'
    assert len(record['life']['activities'])==2 and len(record['life']['photos'])==2
    assert [a['kind'] for a in record['life']['activities']]==['food','food']
    assert record['life']['activities'][0]['media_ids']!=record['life']['activities'][1]['media_ids']
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ContentRecord).where(ContentRecord.type_id==t['id']))==1
        job=db.get(ExchangeJob,row['id']);ids=[e['id'] for e in job.file_manifest['media'].values()]
        assets=list(db.scalars(select(MediaAsset).where(MediaAsset.id.in_(ids))));assert len(assets)==2
        assert db.scalar(select(func.count()).select_from(MediaAsset))==media_before+2
        assert {x.sha256 for x in assets}=={jobs.digest(files['photos/plate-a.jpg']),jobs.digest(files['photos/plate-b.jpg'])}
        assert db.get(RecordRevision,(record['id'],1)) is not None
        assert db.get(ExchangeFileOperation,row['id']).state=='completed'
    for asset in assets:
        assert (MEDIA_DIR/'library-v1'/asset.id/'original').read_bytes() in (files['photos/plate-a.jpg'],files['photos/plate-b.jpg'])
    assert client.get('/api/food?q='+t['slug']).json()['total']==0  # Never publish imported drafts.


def test_mid_import_failure_rolls_back_rows_and_returns_owned_files_to_stage(client,monkeypatch):
    t=make_type(client)
    with SessionLocal() as db:
        media_before=db.scalar(select(func.count()).select_from(MediaAsset));places_before=db.scalar(select(func.count()).select_from(Place))
    row,raw,files=prepare(client,t)
    def fail(stage):
        if stage=='records_created':raise RuntimeError('synthetic crash seam')
    monkeypatch.setattr(jobs,'checkpoint',fail)
    r=confirm(client,row);assert r.status_code==503
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ContentRecord).where(ContentRecord.type_id==t['id']))==0
        assert db.scalar(select(func.count()).select_from(MediaAsset))==media_before
        assert db.scalar(select(func.count()).select_from(Place))==places_before
        job=db.get(ExchangeJob,row['id']);assert job.state=='failed'
        assert db.get(ExchangeFileOperation,row['id']).state=='rolled_back'
        for item in job.file_manifest['media'].values():
            assert jobs.stage_dir(MEDIA_DIR,row['id'],item['id']).is_dir()
            assert not jobs.library_dir(MEDIA_DIR,item['id']).exists()
    monkeypatch.setattr(jobs,'checkpoint',lambda _:None)
    retry=confirm(client,row);assert retry.status_code==200,retry.text
    assert len(retry.json()['result_ids'])==1


def test_schema_change_and_missing_confirmation_are_rejected_without_assets(client):
    t=make_type(client)
    with SessionLocal() as db:media_before=db.scalar(select(func.count()).select_from(MediaAsset))
    row,raw,files=prepare(client,t)
    url='/api/admin/exchange/jobs/'+row['id']+'/confirm'
    assert client.post(url,headers=csrf(client),json={'expected_revision':1,'confirmation':'publish'}).status_code==422
    from test_content import type_payload,write
    changed=type_payload(t,name='新配置');assert write(client,'/types/'+t['id'],changed,'put').status_code==200
    assert confirm(client,row).status_code==409
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(MediaAsset))==media_before


def test_mapping_requires_revision_and_cannot_replace_owned_photo_bytes(client):
    t=make_type(client);row,raw,files=prepare(client,t)
    url='/api/admin/exchange/jobs/'+row['id']+'/mapping'
    content=row['input'];content['records'][0]['title']='用户映射后的标题'
    r=client.put(url,headers=csrf(client),json={'expected_revision':row['revision'],'content':content})
    assert r.status_code==200,r.text
    mapped=r.json();assert mapped['revision']==row['revision']+1
    assert confirm(client,row).status_code==409
    assert client.put(url,headers=csrf(client),json={'expected_revision':row['revision'],'content':content}).status_code==409
    content['media'][0]['path']='photos/not-uploaded.jpg'
    assert client.put(url,headers=csrf(client),json={'expected_revision':mapped['revision'],'content':content}).status_code==422
    done=confirm(client,mapped);assert done.status_code==200,done.text
    record=client.get('/api/admin/content/records/'+done.json()['result_ids'][0]).json()
    assert record['title']=='用户映射后的标题'


def test_cancel_preserves_original_resources_and_blocks_preview_and_confirmation(client):
    t=make_type(client);row,raw,files=prepare(client,t)
    with SessionLocal() as db:before=db.scalar(select(func.count()).select_from(MediaAsset))
    endpoint='/api/admin/exchange/jobs/'+row['id']+'/cancel'
    assert client.post(endpoint,headers=csrf(client),json={'expected_revision':row['revision']+1}).status_code==409
    result=client.post(endpoint,headers=csrf(client),json={'expected_revision':row['revision']})
    assert result.status_code==200 and result.json()['state']=='cancelled'
    assert client.post(endpoint,headers=csrf(client),json={'expected_revision':row['revision']}).status_code==200
    assert confirm(client,row).status_code==409
    assert client.get(row['images'][0]['url']).status_code==404
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(MediaAsset))==before
        assert db.scalar(select(func.count()).select_from(ContentRecord).where(ContentRecord.type_id==t['id']))==0


def test_commit_response_loss_replays_without_duplicating_or_removing_photos(client,monkeypatch):
    t=make_type(client);row,raw,files=prepare(client,t)
    def fail(stage):
        if stage=='db_committed':raise RuntimeError('synthetic lost commit response')
    monkeypatch.setattr(jobs,'checkpoint',fail)
    result=confirm(client,row);assert result.status_code==200,result.text
    assert result.json()['replayed']
    replay=confirm(client,row);assert replay.status_code==200
    assert replay.json()['result_ids']==result.json()['result_ids']
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ContentRecord).where(ContentRecord.type_id==t['id']))==1
        job=db.get(ExchangeJob,row['id'])
        assert db.get(ExchangeFileOperation,row['id']).state=='completed'
        for entry in job.file_manifest['media'].values():
            assert db.get(MediaAsset,entry['id']) is not None
            jobs.verify_files(jobs.library_dir(MEDIA_DIR,entry['id']),entry['files'])


def test_process_death_after_file_rename_releases_locks_and_replays_journal(client):
    from test_api import engine
    if engine.dialect.name!='postgresql':pytest.skip('Requires actual PostgreSQL process locks')
    import os,subprocess,sys
    t=make_type(client);row,raw,files=prepare(client,t)
    with SessionLocal() as db:actor=db.get(ExchangeJob,row['id']).actor_id
    repo=Path(__file__).resolve().parents[1];env=os.environ.copy();env['PYTHONPATH']=str(repo/'backend')
    process=subprocess.run([sys.executable,str(repo/'tests/exchange_process_probe.py'),'--job',row['id'],'--actor',str(actor),'--revision',str(row['revision']),'--root',str(MEDIA_DIR)],env=env,timeout=20,capture_output=True)
    assert process.returncode==73,'Process did not reach the expected durable failure seam'
    with SessionLocal() as db:
        job=db.get(ExchangeJob,row['id']);assert job.state=='confirming'
        assert db.scalar(select(func.count()).select_from(ContentRecord).where(ContentRecord.type_id==t['id']))==0
        for entry in job.file_manifest['media'].values():
            assert db.get(MediaAsset,entry['id']) is None
            jobs.verify_files(jobs.library_dir(MEDIA_DIR,entry['id']),entry['files'])
    from app.exchange.backup import inventory
    with SessionLocal() as db:
        pending=inventory(db,MEDIA_DIR)
        assert {e['id'] for e in db.get(ExchangeJob,row['id']).file_manifest['media'].values()}<=pending
    result=confirm(client,row);assert result.status_code==200,result.text
    assert len(result.json()['result_ids'])==1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ContentRecord).where(ContentRecord.type_id==t['id']))==1
        assert db.get(ExchangeFileOperation,row['id']).state=='completed'



def test_backup_inventory_checks_every_owned_staging_byte_without_promoting_files(client):
    from app.exchange.backup import inventory
    t=make_type(client);row,raw,files=prepare(client,t)
    with SessionLocal() as db:
        assert not inventory(db,MEDIA_DIR)
        entry=next(iter(db.get(ExchangeJob,row['id']).file_manifest['media'].values()))
    folder=jobs.stage_dir(MEDIA_DIR,row['id'],entry['id'])
    unexpected=folder/'not-in-journal.txt'
    unexpected.write_bytes(b'synthetic-unknown')
    try:
        with SessionLocal() as db:
            with pytest.raises(RuntimeError,match='完整性异常'):inventory(db,MEDIA_DIR)
    finally:unexpected.unlink()  # Only the exact synthetic file created by this test.
    with SessionLocal() as db:
        assert not inventory(db,MEDIA_DIR)
        assert db.get(MediaAsset,entry['id']) is None
    jobs.verify_files(folder,entry['files'])


def test_multiple_drafts_share_one_photo_identity_and_support_local_cross_links(client):
    import copy
    t=make_type(client);raw,files=packet(t);value=json.loads(files['travel.json'])
    other=copy.deepcopy(value['records'][0]);other['key']='second';other['title']='第二篇合成内容'
    first=value['records'][0];first['links']=[{'record_key':'second','label':'同一组照片'}];other['links']=[{'record_key':first['key'],'label':'同一组照片'}]
    value['records'].append(other);files['travel.json']=json.dumps(value).encode();stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    with SessionLocal() as db:before=db.scalar(select(func.count()).select_from(MediaAsset))
    response=client.post('/api/admin/exchange/preview',headers=csrf(client)|{'X-Import-Key':str(uuid.uuid4())},files={'file':('shared.zip',stream.getvalue())})
    assert response.status_code==200,response.text
    row=response.json();assert row['valid']
    result=confirm(client,row);assert result.status_code==200,result.text
    ids=result.json()['result_ids'];assert len(ids)==2
    records=[client.get('/api/admin/content/records/'+id).json() for id in ids]
    assert {m['id'] for m in records[0]['connections']['media']}=={m['id'] for m in records[1]['connections']['media']}
    assert records[0]['connections']['links'][0]['id']==ids[1]
    assert records[1]['connections']['links'][0]['id']==ids[0]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(MediaAsset))==before+2
        assert all(db.get(RecordRevision,(id,1)) is not None for id in ids)


def test_final_transaction_rechecks_files_after_a_competing_recovery_move(client,monkeypatch):
    t=make_type(client);row,raw,files=prepare(client,t)
    with SessionLocal() as db:
        entries=list(db.get(ExchangeJob,row['id']).file_manifest['media'].values())
        before=db.scalar(select(func.count()).select_from(MediaAsset))
    def competing_recovery(stage):
        if stage=='files_ready':
            # Synthetic relocation before final lock acquisition; no DB index
            # may be committed against the now-missing library file.
            source=jobs.library_dir(MEDIA_DIR,entries[0]['id']);target=jobs.stage_dir(MEDIA_DIR,row['id'],entries[0]['id']);source.rename(target)
    monkeypatch.setattr(jobs,'checkpoint',competing_recovery)
    response=confirm(client,row);assert response.status_code==409,response.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(MediaAsset))==before
        assert db.scalar(select(func.count()).select_from(ContentRecord).where(ContentRecord.type_id==t['id']))==0
        for entry in entries:jobs.verify_files(jobs.stage_dir(MEDIA_DIR,row['id'],entry['id']),entry['files'])
    monkeypatch.setattr(jobs,'checkpoint',lambda _:None)
    updated=client.get('/api/admin/exchange/jobs/'+row['id']).json()
    # A refreshed revision becomes the identity of this recovery attempt too.
    def lost(stage):
        if stage=='files_ready':raise RuntimeError('synthetic retry interruption')
    monkeypatch.setattr(jobs,'checkpoint',lost)
    assert confirm(client,updated).status_code==503
    monkeypatch.setattr(jobs,'checkpoint',lambda _:None)
    assert confirm(client,updated).status_code==200


def test_structured_places_reuse_existing_category_alias_without_creating_duplicate(client):
    t=make_type(client);raw,files=packet(t);value=json.loads(files['travel.json']);p=value['places'][0];p['name']='合成餐厅-'+t['slug'];p['city']='合成城市'
    existing=client.post('/api/admin/archive/places',headers=csrf(client),json={'name':p['name'],'city':p['city'],'category':'restaurant'})
    assert existing.status_code==200,existing.text
    id=existing.json()['id'];files['travel.json']=json.dumps(value).encode();stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    response=client.post('/api/admin/exchange/preview',headers=csrf(client)|{'X-Import-Key':str(uuid.uuid4())},files={'file':('reuse-place.zip',stream.getvalue())})
    assert response.status_code==200,response.text
    row=response.json();plan=next(x for x in row['planned_places'] if x['key']==p['key'])
    assert plan['action']=='reuse' and plan['existing_id']==id and plan['city']=='合成城市'
    done=confirm(client,row);assert done.status_code==200,done.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Place).where(Place.name==p['name']))==1
        assert db.get(Place,id).revision==1


def test_original_upload_repairs_missing_owned_staging_files_after_known_rollback(client):
    t=make_type(client);key=str(uuid.uuid4());row,raw,files=prepare(client,t,key)
    with SessionLocal() as db:entry=next(iter(db.get(ExchangeJob,row['id']).file_manifest['media'].values()))
    thumbnail=jobs.stage_dir(MEDIA_DIR,row['id'],entry['id'])/'thumbnail.webp'
    thumbnail.unlink()  # Only an exact synthetic staging file created by this case.
    assert confirm(client,row).status_code==409
    repaired=client.post('/api/admin/exchange/preview',headers=csrf(client)|{'X-Import-Key':key},files={'file':('trip.zip',raw)})
    assert repaired.status_code==200,repaired.text
    assert repaired.json()['id']==row['id'] and repaired.json()['state']=='preview'
    jobs.verify_files(thumbnail.parent,entry['files'])
    result=confirm(client,repaired.json());assert result.status_code==200,result.text
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(ContentRecord).where(ContentRecord.type_id==t['id']))==1


def test_expired_preview_is_invalid_and_hides_photos_without_deleting_owned_files(client):
    from datetime import timedelta
    from app.models import now
    t=make_type(client);row,_,_=prepare(client,t)
    with SessionLocal() as db:
        saved=db.get(ExchangeJob,row['id']);saved.expires_at=now()-timedelta(seconds=1)
        entries=list(saved.file_manifest['media'].values());db.commit()
    response=client.get('/api/admin/exchange/jobs/'+row['id']);assert response.status_code==200
    expired=response.json();assert expired['expired'] and not expired['valid'] and expired['images']==[]
    assert confirm(client,expired).status_code==410
    for entry in entries:jobs.verify_files(jobs.stage_dir(MEDIA_DIR,row['id'],entry['id']),entry['files'])


def test_rules_changed_during_file_placement_reject_final_commit_and_allow_explicit_remap(client,monkeypatch):
    from app.blog_models import SiteConfig
    from app.exchange.settings import read as read_settings,KEY
    t=make_type(client);row,_,_=prepare(client,t)
    with SessionLocal() as db:before=db.scalar(select(func.count()).select_from(MediaAsset))
    def change_rules(stage):
        if stage!='files_ready':return
        with SessionLocal() as db:
            jobs.write_lock(db);_,config=read_settings(db);value=config.model_dump(mode='json')
            value['rules']['content_types'][t['slug']]={'style':'确认移动文件期间，另一个管理员修改了规则。'}
            saved=db.scalar(select(SiteConfig).where(SiteConfig.key==KEY))
            if saved:saved.value=value;saved.revision+=1
            else:db.add(SiteConfig(id=str(uuid.uuid4()),key=KEY,value=value,revision=1))
            db.commit()
    monkeypatch.setattr(jobs,'checkpoint',change_rules)
    response=confirm(client,row);assert response.status_code==409,response.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ContentRecord).where(ContentRecord.type_id==t['id']))==0
        assert db.scalar(select(func.count()).select_from(MediaAsset))==before
        saved=db.get(ExchangeJob,row['id']);assert saved.state=='failed'
        assert db.get(ExchangeFileOperation,row['id']).state=='rolled_back'
        for entry in saved.file_manifest['media'].values():jobs.verify_files(jobs.stage_dir(MEDIA_DIR,row['id'],entry['id']),entry['files'])
    fresh=client.get('/api/admin/exchange/jobs/'+row['id']).json();assert fresh['stale_context'] and not fresh['valid']
    assert confirm(client,fresh).status_code==409
    monkeypatch.setattr(jobs,'checkpoint',lambda _:None)
    mapped=client.put('/api/admin/exchange/jobs/'+row['id']+'/mapping',headers=csrf(client),json={'expected_revision':fresh['revision'],'content':fresh['input']})
    assert mapped.status_code==200 and mapped.json()['valid'],mapped.text
    assert confirm(client,mapped.json()).status_code==200
