"""Private inter-container requests must never be sent to an inherited HTTP proxy."""
import json,os,subprocess
from pathlib import Path

def test_nas_internal_proxy_exclusions_and_loopback_health():
    env={**os.environ,'POSTGRES_PASSWORD':'synthetic-config-only','IMAGE_TAG':'synthetic-fixed-version','POSTGRES_IMAGE':'postgres:17-alpine','NO_PROXY':'example.invalid','no_proxy':'example.invalid'}
    result=subprocess.run(['docker','--host=unix:///var/run/docker.sock','compose','--env-file',str(Path(__file__).parents[1]/'.env.nas.example'),'-f',str(Path(__file__).parents[1]/'compose.nas.yaml'),'config','--format','json'],env=env,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,'Compose config validation failed (sensitive output withheld)'
    services=json.loads(result.stdout)['services'];web=services['web']
    assert web['environment']['NO_PROXY']=='example.invalid,api,db,maintenance,web'
    assert web['environment']['no_proxy']=='example.invalid,api,db,maintenance,web'
    assert web['healthcheck']['test']==['CMD','wget','-q','-Y','off','--spider','http://127.0.0.1/']
    assert not services['api'].get('ports') and not services['db'].get('ports')
    assert all(p['host_ip']=='127.0.0.1' for p in web['ports'])


def test_nas_requires_independently_prepared_database_and_never_pulls():
    import yaml
    root=Path(__file__).parents[1]
    nas=yaml.safe_load((root/'compose.nas.yaml').read_text())['services']
    offline=yaml.safe_load((root/'compose.offline.yaml').read_text())['services']
    assert nas['db']['image'].startswith('${POSTGRES_IMAGE:?Prepare an existing PostgreSQL 17 image')
    assert all(nas[r]['pull_policy']=='never' and offline[r]['pull_policy']=='never' for r in nas)
    assert len({nas[r]['image'] for r in ('api','web','maintenance')})==1
    assert nas['maintenance']['depends_on']['db']['condition']=='service_healthy'
    assert nas['api']['depends_on']['maintenance']['condition']=='service_healthy'
    assert nas['web']['depends_on']['api']['condition']=='service_healthy'
