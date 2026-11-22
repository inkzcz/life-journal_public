from pathlib import Path
import importlib.util
import subprocess
import pytest
import yaml


@pytest.fixture
def installation_driver():
    path=Path(__file__).resolve().parent/'docker_installation.py'
    spec=importlib.util.spec_from_file_location('compose_validation_under_test',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def validation_settings(tmp_path):
    base=tmp_path/'private'/'install';base.mkdir(parents=True)
    for name in ('postgres','media','backups'):(base/name).mkdir()
    values={'POSTGRES_DB':'lj_validation','POSTGRES_USER':'lj_validation',
        'POSTGRES_PASSWORD':'synthetic','SETUP_KEY':'test'*10,'COOKIE_SECURE':'false',
        'IMAGE_TAG':'v5.1.9-candidate.test','POSTGRES_IMAGE':'postgres:17-alpine',
        'WEB_BIND_IP':'127.0.0.1','WEB_PORT':'0',
        'DB_DATA_DIR':str(base/'postgres'),'MEDIA_DATA_DIR':str(base/'media'),
        'BACKUP_DATA_DIR':str(base/'backups')}
    path=base/'.env';path.write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
    return path,values


def test_validation_compose_never_inherits_operator_deployment_settings(installation_driver,validation_settings,monkeypatch):
    driver=installation_driver;path,values=validation_settings
    for key in values:monkeypatch.setenv(key,'operator-value')
    for key in ('COMPOSE_FILE','COMPOSE_ENV_FILES','COMPOSE_PROJECT_NAME','COMPOSE_PROFILES',
                'DATABASE_URL','AUTO_MIGRATE_ON_STARTUP','AUTO_MIGRATION_RETRY_TOKEN',
                'MIGRATION_WAIT_SECONDS','NO_PROXY','no_proxy'):
        monkeypatch.setenv(key,'operator-value')
    calls=[]
    def fake(args,**kwargs):
        calls.append((args,kwargs));return subprocess.CompletedProcess(args,0,'{}','')
    monkeypatch.setattr(driver.subprocess,'run',fake)
    assert driver.compose('lj-install-0123456789',path,'config','--format','json')=='{}'
    child=calls[0][1]['env']
    assert all(child[k]==v for k,v in values.items())
    assert child['AUTO_MIGRATE_ON_STARTUP']=='true' and child['AUTO_MIGRATION_RETRY_TOKEN']==''
    assert child['MIGRATION_WAIT_SECONDS']=='1800' and child['NO_PROXY']=='localhost,127.0.0.1'
    assert not any(k.startswith('COMPOSE_') for k in child) and 'DATABASE_URL' not in child
    assert calls[0][0][-3:]==('config','--format','json')


@pytest.mark.parametrize('change',[
    ('DB_DATA_DIR','/synthetic-outside-validation'),('WEB_BIND_IP','0.0.0.0'),
    ('COMPOSE_FILE','/synthetic-operator-compose.yaml'),
])
def test_validation_rejects_settings_that_escape_isolation(installation_driver,validation_settings,change,monkeypatch):
    path,values=validation_settings;values[change[0]]=change[1]
    path.write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
    monkeypatch.setattr(installation_driver.subprocess,'run',lambda *a,**k:pytest.fail('Docker must not be invoked'))
    with pytest.raises(RuntimeError):installation_driver.compose('lj-install-0123456789',path,'up','-d')


def test_validation_rejects_symlink_data_directory(installation_driver,validation_settings,tmp_path):
    path,values=validation_settings
    target=Path(values['MEDIA_DATA_DIR']);target.rmdir()
    outside=tmp_path/'outside';outside.mkdir();target.symlink_to(outside,target_is_directory=True)
    with pytest.raises(RuntimeError,match='private test directory'):installation_driver.compose_environment(path)


def test_validation_rejects_preexisting_project_before_start(installation_driver,monkeypatch):
    calls=[]
    def fake(*args,**kwargs):calls.append(args);return 'synthetic-existing-container\n'
    monkeypatch.setattr(installation_driver,'run',fake)
    with pytest.raises(RuntimeError,match='already has containers'):
        installation_driver.require_unused_project('lj-install-0123456789')
    assert len(calls)==1 and calls[0][:3]==('docker','ps','--all')


def test_validation_cleanup_attempts_all_projects_and_never_masks_failure(installation_driver,validation_settings,monkeypatch):
    path,_=validation_settings;calls=[]
    def fake(name,*args,**kwargs):
        calls.append(name)
        if name.startswith('lj-restore-'):raise RuntimeError('Synthetic stop failure')
        return ''
    monkeypatch.setattr(installation_driver,'compose',fake)
    with pytest.raises(RuntimeError,match='cleanup incomplete'):
        installation_driver.stop_projects([('lj-install-0123456789',path,None),('lj-restore-0123456789',path,None)])
    assert calls==['lj-restore-0123456789','lj-install-0123456789']


def test_validation_rejects_unrelated_project_without_docker(installation_driver,validation_settings,monkeypatch):
    path,_=validation_settings
    monkeypatch.setattr(installation_driver.subprocess,'run',lambda *a,**k:pytest.fail('Docker must not be invoked'))
    with pytest.raises(RuntimeError,match='namespace'):installation_driver.compose('unrelated-project',path,'stop')


def test_validation_existing_report_stops_before_docker(installation_driver,tmp_path,monkeypatch):
    report=tmp_path/'report.json';report.write_text('existing evidence')
    monkeypatch.setattr(installation_driver.sys,'argv',['docker_installation.py','--image-tag','v5.1.9-candidate.test','--output',str(report)])
    monkeypatch.setattr(installation_driver.subprocess,'run',lambda *a,**k:pytest.fail('Docker must not be invoked'))
    with pytest.raises(SystemExit,match='already exists'):installation_driver.main()
    assert report.read_text()=='existing evidence'

def test_private_ports_and_persistent_volumes():
    config = yaml.safe_load((Path(__file__).parents[1] / 'compose.yaml').read_text())
    services = config['services']
    assert 'ports' not in services['db']
    assert 'ports' not in services['api']
    assert services['web']['ports']==['${WEB_BIND_IP:-127.0.0.1}:${WEB_PORT:-18080}:80']
    assert '${DB_DATA_DIR:-./postgres}:/var/lib/postgresql/data' in services['db']['volumes']
    assert '${MEDIA_DATA_DIR:-./media}:/data/media' in services['api']['volumes']
    assert services['api']['depends_on']['db']['condition'] == 'service_healthy'


def test_automatic_upgrade_dependency_order_and_mount_boundaries():
    for filename in ['compose.yaml','compose.nas.yaml']:
        config=yaml.safe_load((Path(__file__).parents[1]/filename).read_text())
        services=config['services']
        assert set(services)=={'db','maintenance','api','web'}
        assert services['maintenance']['depends_on']=={'db':{'condition':'service_healthy'}}
        assert services['api']['depends_on']['maintenance']=={'condition':'service_healthy'}
        assert services['web']['depends_on']=={'api':{'condition':'service_healthy'}}
        assert services['maintenance']['environment']['AUTO_MIGRATE_ON_STARTUP']=='${AUTO_MIGRATE_ON_STARTUP:-true}'
        assert services['maintenance']['healthcheck']['start_period']=='30m'
        assert not any('backups' in v or 'docker.sock' in v for v in services['api']['volumes'])
        assert 'ports' not in services['maintenance']
