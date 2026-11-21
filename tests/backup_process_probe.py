"""Subprocess actor for bounded, real OS/PG lock races (synthetic storage only).
The dump hook emits unit bytes; actual PG17 dump/restore is separately exercised
by the Compose disaster drill. No test process prints credentials or SQL values.
"""
import json,os,sys,time
from pathlib import Path
from contextlib import contextmanager
from app import backup
from app.db import engine,SessionLocal
from app import maintenance_worker as worker
mode,id,signal_dir=sys.argv[1:]
control=Path(signal_dir)
def pause():
    (control/'ready').touch()
    for _ in range(1000):
        if (control/'release').exists():return
        time.sleep(.02)
    raise RuntimeError('bounded probe timeout')
original=backup.subprocess.run
def dump(args,**kwargs):
    if args[0]=='pg_dump':
        Path(args[args.index('--file')+1]).write_bytes(b'synthetic concurrency unit dump')
        pause();return
    return original(args,**kwargs)
try:
    if mode in {'create','job'}:
        backup.subprocess.run=dump
        if mode=='create':backup.create_backup(id)
        else:
            freeze=backup.frozen
            @contextmanager
            def gated(bind):
                pause()  # root lock held, before PG exclusive: race job claiming too
                with freeze(bind) as con:yield con
            backup.frozen=gated
            worker.supervised=lambda action:backup.create_backup()
            worker.run_job(id)
    elif mode in {'verify','restore'}:
        verify=backup.verify
        def reading(*a,**k):
            m=verify(*a,**k);pause();return m
        backup.verify=reading
        if mode=='restore':backup.restore(id,True)
        else:
            with backup.backup_lock(id=id):backup.verify(id)
    elif mode=='retain':
        import shutil
        remove=shutil.rmtree
        def interrupted(path):
            # Deliberately interrupt only an eligible old copy, after one file.
            (Path(path)/'database.dump').unlink();pause();remove(path)
        shutil.rmtree=interrupted
        with SessionLocal() as db:worker.retain(db,1)
    elif mode=='frozen':
        with backup.frozen(engine):pause()
    elif mode=='leader':
        from sqlalchemy import text
        with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as con:
            assert con.scalar(text(f'SELECT pg_try_advisory_lock({worker.LEADER})'))
            pause()
    elif mode=='tick':worker.leader_loop(once=True)
    print(json.dumps({'state':'completed'}),flush=True)
except backup.BackupError as e:
    print(json.dumps({'state':'rejected','reason':str(e)}),flush=True)
