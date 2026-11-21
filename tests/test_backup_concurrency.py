"""Real process-level flock/PG races, each actor bounded to <=25 seconds."""
import os,json,subprocess,sys,time,uuid
from pathlib import Path
from datetime import datetime,timedelta,timezone
from contextlib import contextmanager
import pytest
from sqlalchemy import select,delete,text
from test_backup import storage,artifact
from test_content import client
from test_api import engine,SessionLocal
from app import backup
from app.maintenance_worker import catalog,retain,discover
from app.recovery_models import BackupArtifact,MaintenanceJob
from app.services.maintenance import enqueue
from app.services.write_barrier import writer

pytestmark=pytest.mark.skipif(engine.dialect.name!='postgresql',reason='Real PostgreSQL process lock tests')

@contextmanager
def actor(tmp_path,mode,id='',wait=True):
    signal=tmp_path/uuid.uuid4().hex;signal.mkdir()
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'backend')}
    p=subprocess.Popen([sys.executable,str(Path(__file__).with_name('backup_process_probe.py')),mode,id,str(signal)],env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    try:
        if wait:
            for _ in range(500):
                if (signal/'ready').exists():break
                assert p.poll() is None,'probe exited before acquiring lock'
                time.sleep(.02)
            else:raise AssertionError('bounded readiness timeout')
        yield p,signal
    finally:
        if p.poll() is None:p.kill()
        p.communicate(timeout=5)

def finish(p,signal):
    (signal/'release').touch();out,_=p.communicate(timeout=25);assert p.returncode==0
    return json.loads(out)

def wait_for_server_lock_release(key, *, shared=False):
    # Client waitpid does not wait for the remote PostgreSQL backend to process
    # EOF. Observe actual lock availability, never weaken the production gate.
    suffix='_shared' if shared else ''
    deadline=time.monotonic()+5
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as con:
        while time.monotonic()<deadline:
            if con.scalar(text(f'SELECT pg_try_advisory_lock{suffix}({key})')):
                con.scalar(text(f'SELECT pg_advisory_unlock{suffix}({key})'))
                return
            time.sleep(.02)
    raise AssertionError('PostgreSQL did not release the dead actor lock within 5 seconds')


def copies(storage):
    # Keep this catalog local to these synthetic files, never a deployment DB.
    with SessionLocal() as db:
        db.execute(delete(BackupArtifact));db.commit();ids=[]
        for i in range(4):
            m=artifact(storage,datetime.now(timezone.utc)-timedelta(days=10-i));catalog(db,m);ids.append(m['id'])
        db.get(BackupArtifact,ids[0]).restored_at=datetime.now(timezone.utc);db.commit()
    return ids

@pytest.mark.parametrize('mode',['create','verify','restore'])
def test_active_operation_defers_retention_process(storage,client,tmp_path,mode):
    ids=copies(storage);target=str(uuid.uuid4()) if mode=='create' else ids[1]
    before={id:backup.files(storage[0]/id) for id in ids}
    with actor(tmp_path,mode,target) as (p,signal):
        with SessionLocal() as db:assert retain(db,1)['state']=='deferred'
        assert all(backup.files(storage[0]/id)==before[id] for id in ids)
        result=finish(p,signal)
        assert result['state']==('rejected' if mode=='restore' else 'completed')
        if mode=='restore':assert '非空' in result['reason']
    with SessionLocal() as db:assert retain(db,1)['state']=='succeeded'
    assert (storage[0]/ids[0]).is_dir() and (storage[0]/ids[-1]).is_dir()


def test_two_process_backups_and_killed_partial_release_locks(storage,client,tmp_path):
    ids=copies(storage);a,b=str(uuid.uuid4()),str(uuid.uuid4())
    with actor(tmp_path,'create',a) as (p,signal):
        with actor(tmp_path,'create',b,wait=False) as (other,other_signal):
            rejected=finish(other,other_signal);assert rejected['state']=='rejected' and '目录忙' in rejected['reason']
        assert not (storage[0]/a).exists() and not (storage[0]/b).exists()
        p.kill();p.wait(timeout=5)
    assert (storage[0]/('.partial-'+a)).exists() and not (storage[0]/a).exists()
    for id in ids:backup.verify(id)
    with SessionLocal() as db:
        discover(db);assert db.get(BackupArtifact,a) is None and db.get(BackupArtifact,b) is None
    # Both flock and PG exclusive lock are released after SIGKILL.
    with backup.backup_lock(exclusive=True),writer(engine):pass


def test_cleanup_process_interruption_never_touches_drill_or_newest(storage,client,tmp_path):
    ids=copies(storage);protected={id:backup.files(storage[0]/id) for id in [ids[0],ids[-1]]}
    with actor(tmp_path,'retain') as (p,signal):
        with pytest.raises(backup.BackupError,match='目录忙'):
            with backup.backup_lock(id=ids[-1]):pass
        p.kill();p.wait(timeout=5)
    assert all(backup.files(storage[0]/id)==data for id,data in protected.items())
    with SessionLocal() as db:assert retain(db,1)['state']=='deferred'  # damaged old copy blocks more eviction
    assert all((storage[0]/id).is_dir() for id in ids)
    with backup.backup_lock(exclusive=True),writer(engine):pass


def test_corrupt_backup_and_latest_actual_drill_are_conservative(storage,client):
    ids=copies(storage)
    with SessionLocal() as db:
        # Last performed drill, not the newest backup creation time, wins.
        db.get(BackupArtifact,ids[1]).restored_at=datetime.now(timezone.utc)-timedelta(days=1);db.commit()
        (storage[0]/ids[2]/'database.dump').write_bytes(b'corrupt')
        assert retain(db,1)['state']=='deferred'
        assert all((storage[0]/id).exists() for id in ids)
        m=backup.verify(ids[0]);assert m['id']==ids[0]


def test_manual_and_due_jobs_race_without_false_success(storage,client,tmp_path):
    copies(storage)
    with SessionLocal() as db:
        a=enqueue(db,'backup');b=enqueue(db,'backup',dedupe='backup:synthetic-due-'+uuid.uuid4().hex);db.commit();ids=a.id,b.id
    with actor(tmp_path,'job',ids[0]) as (p,signal):
        with actor(tmp_path,'job',ids[1],wait=False) as (q,other):finish(q,other)
        with SessionLocal() as db:
            assert db.get(MaintenanceJob,ids[1]).state=='failed'
            assert '目录忙' in db.get(MaintenanceJob,ids[1]).error
        finish(p,signal)
    with SessionLocal() as db:
        assert db.get(MaintenanceJob,ids[0]).state=='succeeded'
        assert db.get(MaintenanceJob,ids[1]).state=='failed'
        assert not db.get(MaintenanceJob,ids[1]).result.get('backup_id')


def test_shared_file_lock_failure_and_pg_owner_death(storage,client,tmp_path):
    ids=copies(storage)
    with actor(tmp_path,'frozen') as (p,signal):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            with writer(engine):pass
        p.kill();p.wait(timeout=5)
    from app.services.write_barrier import KEY
    wait_for_server_lock_release(KEY,shared=True)
    with writer(engine):pass
    with actor(tmp_path,'leader') as (p,signal):
        with actor(tmp_path,'tick',wait=False) as (q,s):assert finish(q,s)['state']=='completed'
        p.kill();p.wait(timeout=5)
    from sqlalchemy import text
    from app.maintenance_worker import LEADER
    wait_for_server_lock_release(LEADER)
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as con:
        assert con.scalar(text(f'SELECT pg_try_advisory_lock({LEADER})'))
        con.scalar(text(f'SELECT pg_advisory_unlock({LEADER})'))


def test_duplicate_job_claim_only_executes_once(storage,client,tmp_path):
    copies(storage)
    with SessionLocal() as db:
        j=enqueue(db,'backup');db.commit();id=j.id
    with actor(tmp_path,'job',id) as (p,signal):
        with actor(tmp_path,'job',id,wait=False) as (q,s):assert finish(q,s)['state']=='completed'
        with SessionLocal() as db:assert db.get(MaintenanceJob,id).state=='running'
        finish(p,signal)
    with SessionLocal() as db:
        row=db.get(MaintenanceJob,id);assert row.state=='succeeded' and row.result['backup_id']


def test_last_actual_drill_time_is_protected_not_newest_creation(storage,client):
    ids=copies(storage)
    with SessionLocal() as db:
        db.get(BackupArtifact,ids[1]).restored_at=datetime.now(timezone.utc)-timedelta(days=1);db.commit()
        assert retain(db,1)['state']=='succeeded'
    assert (storage[0]/ids[0]).is_dir() and (storage[0]/ids[-1]).is_dir()
    assert not (storage[0]/ids[1]).exists()
