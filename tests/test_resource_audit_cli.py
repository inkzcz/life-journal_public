"""The explicit audit command never rewrites bodies, snapshots or files."""
import json
from test_migrations import migration_db,cli
from app.migrations import upgrade

def test_explicit_resource_audit_cli_checks_both_resources(migration_db):
    upgrade(migration_db)
    result=cli(migration_db,'app.services.resource_usage')
    assert result.returncode==0,result.stderr
    value=json.loads(result.stdout)
    assert value=={'media':{'media_version':1,'issues':[]},'places':{'version':1,'issues':[]}}
