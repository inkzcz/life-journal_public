"""Integrity/security/scheduler unit tests; real pg_dump/restore runs separately."""
import json,uuid,subprocess
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from sqlalchemy import select,text
from test_content import client
from test_api import csrf,SessionLocal,engine,reset_limiter
from app import backup
from app.recovery_models import BackupArtifact
from app.services.maintenance import next_backup
from app.services.write_barrier import frozen,writer
from app.maintenance_worker import catalog,retain

@pytest.fixture
def storage(tmp_path,monkeypatch):
    root=tmp_path/'synthetic-hdd';root.mkdir();media=tmp_path/'synthetic-ssd-media'
    # Real DB fixtures need their corresponding synthetic media for consistency validation.
    import shutil
    from test_api import MEDIA_DIR
    if MEDIA_DIR.exists():shutil.copytree(MEDIA_DIR,media)
    else:media.mkdir()
    (root/'.life-journal-target').write_text(backup.MARKER);(root/'.operation.lock').touch()
    monkeypatch.setenv('BACKUP_ROOT',str(root));monkeypatch.setenv('MEDIA_DIR',str(media));monkeypatch.setenv('LIFE_JOURNAL_VERSION','synthetic-unit')
    return root,media

def artifact(storage,created=None):
    root,media=storage;id=str(uuid.uuid4());p=root/id;p.mkdir();(p/'media').mkdir();(p/'database.dump').write_bytes(b'unit fixture, not a pg_dump');(p/'media'/'synthetic.png').write_bytes(b'unit bytes')
    m={'format':1,'complete':True,'id':id,'app_version':'synthetic-unit','schema_version':backup.HEAD,'postgresql_major':17,'created_at':(created or datetime.now(timezone.utc)).isoformat(),'files':backup.files(p),'tables':{}}
    (p/'manifest.json').write_text(json.dumps(m));return m


def test_manifest_integrity_and_no_frontend_paths(storage):
    m=artifact(storage);assert backup.verify(m['id'])['id']==m['id']
    for id in ['../escape','/etc/passwd','not-uuid']:
        with pytest.raises(backup.BackupError):backup.verify(id)
    (storage[0]/m['id']/'media'/'synthetic.png').write_bytes(b'changed')
    with pytest.raises(backup.BackupError):backup.verify(m['id'])


def test_symlinks_and_missing_mount_refused(storage,monkeypatch):
    root,media=storage;m=artifact(storage)
    (root/m['id']/'media'/'unsafe').symlink_to('/etc/passwd')
    with pytest.raises(backup.BackupError):backup.verify(m['id'])
    assert backup.configured()
    (root/'.life-journal-target').unlink();assert backup.configured()  # SSD needs no old HDD marker
    monkeypatch.setenv('BACKUP_ROOT',str(media));assert not backup.configured()


def test_restore_refuses_unconfirmed_nonempty_and_wrong_versions(storage,client,monkeypatch,tmp_path):
    m=artifact(storage)
    empty_target=tmp_path/'empty-restore-media';empty_target.mkdir();monkeypatch.setenv('MEDIA_DIR',str(empty_target))
    with pytest.raises(backup.BackupError,match='确认'):backup.restore(m['id'])
    if engine.dialect.name=='postgresql':
        with pytest.raises(backup.BackupError,match='数据库非空'):backup.restore(m['id'],True)
    else:
        with pytest.raises(RuntimeError,match='仅支持 PostgreSQL'):backup.restore(m['id'],True)
    path=storage[0]/m['id']/'manifest.json';m['app_version']='wrong-version';path.write_text(json.dumps(m))
    with pytest.raises(backup.BackupError,match='不兼容'):backup.restore(m['id'],True)


def test_backup_failure_does_not_publish_or_touch_existing_copy(storage,client,monkeypatch):
    old=artifact(storage);before=backup.files(storage[0]/old['id']);new=str(uuid.uuid4())
    def fail(*a,**kw):raise subprocess.CalledProcessError(1,['pg_dump'])
    monkeypatch.setattr(backup.subprocess,'run',fail)
    if engine.dialect.name=='postgresql':
        with pytest.raises(subprocess.CalledProcessError):backup.create_backup(new)
    else:
        with pytest.raises(RuntimeError,match='仅支持 PostgreSQL'):backup.create_backup(new)
    assert not (storage[0]/new).exists() and backup.files(storage[0]/old['id'])==before
    assert backup.verify(old['id'])['id']==old['id']


def test_retention_keeps_last_drill_verified_and_waits_for_first_drill(storage,client):
    ids=[]
    with SessionLocal() as db:
        for i in range(4):
            m=artifact(storage,datetime.now(timezone.utc)-timedelta(days=20-i));catalog(db,m);ids.append(m['id'])
        db.commit();retain(db,2)
        assert all((storage[0]/id).is_dir() for id in ids)
        db.get(BackupArtifact,ids[0]).restored_at=datetime.now(timezone.utc);db.commit();retain(db,2)
        assert (storage[0]/ids[0]).is_dir() and not (storage[0]/ids[1]).exists()
        assert all((storage[0]/id).is_dir() for id in ids[2:])


def test_writer_freeze_blocks_api_without_losing_content_and_releases(client):
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL writer barrier')
    with frozen(engine):
        assert client.get('/api/admin/content/types').status_code==200
        response=client.post('/api/admin/content/types',headers=csrf(client),json={'name':'blocked synthetic','slug':'blocked-'+uuid.uuid4().hex})
        assert response.status_code==503 and response.headers['retry-after']=='30'
    assert client.post('/api/admin/content/types',headers=csrf(client),json={'name':'safe synthetic','slug':'safe-'+uuid.uuid4().hex}).status_code==200


def test_weekly_timezone_and_dst_single_occurrence():
    config={'timezone':'Asia/Shanghai','weekday':0,'hour':3,'minute':0}
    after=datetime(2026,10,18,0,tzinfo=timezone.utc)
    assert next_backup(config,after)==datetime(2026,10,18,19,tzinfo=timezone.utc)
    config={'timezone':'America/New_York','weekday':6,'hour':1,'minute':30}
    due=next_backup(config,datetime(2026,11,1,0,tzinfo=timezone.utc));assert due==datetime(2026,11,1,5,30,tzinfo=timezone.utc)
    assert next_backup(config,due).date().isoformat()=='2026-11-08'
    config['hour']=2
    assert next_backup(config,datetime(2026,3,8,0,tzinfo=timezone.utc)).date().isoformat()=='2026-03-15'


def test_baked_version_cannot_be_spoofed_by_runtime_env(tmp_path,monkeypatch):
    (tmp_path/'BUILD_VERSION').write_text('release-synthetic-immutable\n')
    monkeypatch.setattr(backup,'__file__',str(tmp_path/'app'/'backup.py'))
    monkeypatch.setenv('LIFE_JOURNAL_VERSION','wrong-runtime-version')
    assert backup.version()=='release-synthetic-immutable'


def test_freeze_exception_releases_shared_writers(client):
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL writer barrier')
    with pytest.raises(RuntimeError):
        with frozen(engine):raise RuntimeError('synthetic failure')
    with writer(engine):pass


def test_scheduler_runs_without_browser_and_leader_is_exclusive(client,monkeypatch):
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL scheduler leadership')
    from app.maintenance_worker import leader_loop,LEADER
    from app.recovery_models import MaintenanceJob
    from app.content_models import ContentRecord
    from test_recovery import deleted
    from test_archive import create_record
    from test_content import make_type
    monkeypatch.setenv('DYNAMIC_BLOG_ENABLED','true')
    t=make_type(client);r=deleted(client,create_record(client,t))
    with SessionLocal() as db:
        row=db.get(ContentRecord,r['id']);row.deleted_at=datetime.now(timezone.utc)-timedelta(days=1000);row.created_at=row.deleted_at-timedelta(days=1);db.commit()
    from app.services.blog import save_config
    with SessionLocal() as db:
        from app.services.maintenance import settings_data
        config=settings_data(db);revision=config.pop('revision');config['cleanup_confirmed']=True;save_config(db,'recovery',config,revision)
        from app.services.maintenance import mark_cleanup_review
        mark_cleanup_review(db,True);db.commit()
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as other:
        other.scalar(text(f'SELECT pg_advisory_lock({LEADER})'))
        leader_loop(once=True)
        with SessionLocal() as db:assert db.get(ContentRecord,r['id']) is not None
        other.scalar(text(f'SELECT pg_advisory_unlock({LEADER})'))
    leader_loop(once=True)
    with SessionLocal() as db:
        assert db.get(ContentRecord,r['id']) is None
        count=db.scalar(select(__import__('sqlalchemy').func.count()).select_from(MaintenanceJob).where(MaintenanceJob.kind=='cleanup'))
    leader_loop(once=True)
    with SessionLocal() as db:assert db.scalar(select(__import__('sqlalchemy').func.count()).select_from(MaintenanceJob).where(MaintenanceJob.kind=='cleanup'))==count


def test_single_complete_directory_does_not_depend_on_root_marker(storage):
    m=artifact(storage);root,_=storage
    (root/'.operation.lock').unlink();(root/'.life-journal-target').unlink()
    assert backup.readable_target() and not backup.configured()
    with backup.backup_lock(id=m['id']):assert backup.verify(m['id'])['complete'] is True


def test_retention_partial_is_not_reported_as_fully_successful_backup_job(storage,client,monkeypatch):
    import app.maintenance_worker as worker
    from app.services.maintenance import enqueue
    from app.recovery_models import MaintenanceJob
    m=artifact(storage)
    monkeypatch.setattr(worker,'supervised',lambda action:m)
    monkeypatch.setattr(worker,'retain',lambda db,keep:{'state':'partial','note':'旧副本清理中断，其余副本保留'})
    with SessionLocal() as db:
        j=enqueue(db,'backup');db.commit();id=j.id
    worker.run_job(id)
    with SessionLocal() as db:
        job=db.get(MaintenanceJob,id)
        assert job.state=='partial' and job.result['file_integrity']=='passed'
        assert job.result['restore_validation']=='not_run' and job.result['retention']['state']=='partial'
        assert db.get(BackupArtifact,m['id']).verified_at is not None


def test_discovery_keeps_writer_barrier_until_catalog_commit(storage,client,monkeypatch):
    from app.maintenance_worker import discover
    from app.services.write_barrier import KEY
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL commit barrier')
    m=artifact(storage)
    with SessionLocal() as db:
        commit=db.commit;checked=[]
        def guarded_commit():
            with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as con:
                acquired=con.scalar(text(f'SELECT pg_try_advisory_lock({KEY})'))
                if acquired:con.scalar(text(f'SELECT pg_advisory_unlock({KEY})'))
                assert not acquired,'backup must not pass discovery before DB commit'
            checked.append(True);commit()
        monkeypatch.setattr(db,'commit',guarded_commit);discover(db)
        assert checked and db.get(BackupArtifact,m['id']) is not None


def test_ssd_target_prepares_without_hdd_marker_and_preserves_existing_files(storage):
    root,_=storage
    (root/'.operation.lock').unlink();(root/'.life-journal-target').unlink()
    m=artifact(storage)
    original=backup.files(root/m['id'])
    backup.prepare_local_target();backup.prepare_local_target()
    assert backup.configured() and not (root/'.life-journal-target').exists()
    assert backup.files(root/m['id'])==original


def test_daily_backup_default_and_weekly_setting_preserved():
    from app.recovery_schemas import RecoverySettings
    config=RecoverySettings().model_dump()
    assert config['frequency']=='daily' and config['hour']==2 and config['keep']==7
    after=datetime(2026,10,21,18,0,tzinfo=timezone.utc)
    assert next_backup(config,after)==datetime(2026,10,22,18,0,tzinfo=timezone.utc)
    weekly={**config,'frequency':'weekly','weekday':0}
    assert next_backup(weekly,after)==datetime(2026,10,25,18,0,tzinfo=timezone.utc)


def test_schedule_save_before_boundary_catches_up_when_worker_polls_late(client,monkeypatch):
    import app.services.maintenance as maintenance
    saved=datetime(2026,10,21,1,59,58,tzinfo=timezone.utc)
    poll=datetime(2026,10,21,2,0,5,tzinfo=timezone.utc)
    config={'frequency':'daily','weekday':0,'hour':2,'minute':0,'timezone':'UTC'}
    with SessionLocal() as db:
        monkeypatch.setattr(maintenance,'db_now',lambda _:saved)
        maintenance.mark_schedule_changed(db,123)
        anchor=maintenance.schedule_anchor(db,123,poll)
        assert next_backup(config,anchor)==datetime(2026,10,21,2,0,tzinfo=timezone.utc)
        assert next_backup(config,anchor)<poll  # execute once now, not tomorrow
        assert maintenance.schedule_anchor(db,124,poll)==poll  # stale metadata ignored
        db.rollback()


def test_system_directory_probe_cannot_write_during_consistent_backup(client):
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL filesystem barrier')
    root=client.app.state.settings.media_dir
    before=backup.files(root)
    with frozen(engine):
        response=client.get('/api/admin/system')
        assert response.status_code==200
        assert response.json()['media_writable'] is None
        assert backup.files(root)==before
    assert client.get('/api/admin/system').json()['media_writable'] is True
    assert backup.files(root)==before


def test_standalone_backup_cli_registers_all_v5_fingerprint_tables():
    # A main-app import masks missing registrations: exercise a fresh CLI process.
    import os,sys
    env=os.environ.copy();env['DATABASE_URL']='sqlite://';env['PYTHONPATH']=str(Path(__file__).parents[1]/'backend')
    code="from app import backup,migrations; assert migrations.V5_TABLES <= set(backup.Base.metadata.tables)"
    result=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,'Standalone backup must fingerprint every v5 table'
