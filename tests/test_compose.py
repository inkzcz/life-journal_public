from pathlib import Path
import yaml

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
