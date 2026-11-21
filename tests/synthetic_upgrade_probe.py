"""Opt-in PG17 drill against a newly created, empty synthetic database only."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path.cwd()))


def main():
    if os.environ.get('RUN_LJ_SYNTHETIC_UPGRADE_DRILL')!='1':
        raise SystemExit('Explicit synthetic upgrade drill opt-in is required')
    from app.db import engine
    from app import auto_migrate as gate,migrations,backup
    from alembic import command
    from auto_migration_compose import SEED
    if engine.dialect.name!='postgresql' or not engine.url.database.startswith('lj_validation_upgrade_'):
        raise SystemExit('Only a dedicated synthetic upgrade database is accepted')
    gate.require_empty(engine)
    media=Path(os.environ['MEDIA_DIR']);backups=Path(os.environ['BACKUP_ROOT'])
    if any(media.iterdir()) or any(p.name!='.operation.lock' for p in backups.iterdir()):
        raise SystemExit('Synthetic media and backup targets must be new and empty')
    with contextlib.redirect_stdout(io.StringIO()):
        exec(SEED,{'__name__':'synthetic_upgrade_seed'})
    with engine.begin() as con:
        command.upgrade(migrations.config(con),'0018_content_exchange')
    original_metadata=gate.metadata(engine)
    before=gate.fingerprint(engine,original_metadata)
    media_before=backup.files(media)
    result=gate.run(engine)
    after=gate.fingerprint(engine,original_metadata)
    before.pop('alembic_version');after.pop('alembic_version')
    assert before==after and backup.files(media)==media_before
    assert result['state']=='upgraded' and result['schema']==migrations.HEAD
    reports=list(backups.glob('.upgrades-v1/*/*/restore-report.json'))
    assert len(reports)==1
    report=json.loads(reports[0].read_text())
    for field in ('backup_restore','media_restore','tables_and_sequences','trial_migration'):
        assert report[field]=='passed'
    assert report['original_values_preserved'] is True
    assert gate.run(engine)['state']=='current'
    print(json.dumps({'synthetic_only':True,'source_schema':'0018_content_exchange',
        'target_schema':migrations.HEAD,'actual_pg17_restore_and_trial':'passed',
        'original_values_and_sequences_preserved':True,'media_files_preserved':len(media_before),
        'repeated_startup':'current','historical_upgrade_001_reproduced':False}))


if __name__=='__main__':main()
