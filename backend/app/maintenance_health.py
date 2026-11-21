"""Read-only maintenance heartbeat healthcheck; no credentials printed."""
import os,json
from .db import SessionLocal,engine
from .services.maintenance import status_data

def main():
    try:
        if os.getenv('AUTO_MIGRATE_ON_STARTUP','false') == 'true':
            from .auto_migrate import READY,build_identity
            from .migrations import HEAD,require_current_schema
            receipt=json.loads(READY.read_text())
            if receipt.get('schema')!=HEAD or receipt.get('build')!=build_identity():raise RuntimeError('startup gate incomplete')
            require_current_schema(engine)
        with SessionLocal() as db:healthy=status_data(db)['online']
    except Exception:healthy=False
    raise SystemExit(0 if healthy else 1)
if __name__=='__main__':main()
