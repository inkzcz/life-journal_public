"""Explicit local-only, synthetic four-container installation and restore drill.

Run after building ONE business image and independently preparing postgres:17-alpine.
All paths/projects are new; only this invocation's containers are stopped. No prune,
image removal, production mounts, public port binding, registry push or data deletion.
"""
import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.command_errors import summarize

ROOT=Path(__file__).resolve().parents[1]
PROCESS_ENV_KEYS=frozenset({
    'PATH','PATHEXT','SystemRoot','SYSTEMROOT','WINDIR','COMSPEC','HOME','USERPROFILE',
    'APPDATA','LOCALAPPDATA','XDG_CONFIG_HOME','TMPDIR','TMP','TEMP',
    'LANG','LC_ALL','LC_CTYPE','DOCKER_CONFIG','DOCKER_HOST','DOCKER_CONTEXT',
    'DOCKER_API_VERSION',
})
VALIDATION_KEYS=frozenset({
    'POSTGRES_DB','POSTGRES_USER','POSTGRES_PASSWORD','SETUP_KEY','COOKIE_SECURE',
    'IMAGE_TAG','POSTGRES_IMAGE','WEB_BIND_IP','WEB_PORT',
    'DB_DATA_DIR','MEDIA_DATA_DIR','BACKUP_DATA_DIR',
})
VALIDATION_DEFAULTS={
    'AUTO_MIGRATE_ON_STARTUP':'true','AUTO_MIGRATION_RETRY_TOKEN':'',
    'MIGRATION_WAIT_SECONDS':'1800','NO_PROXY':'localhost,127.0.0.1',
    'no_proxy':'localhost,127.0.0.1',
}


def run(*args,env=None):
    result=subprocess.run(args,capture_output=True,text=True,timeout=360,env=env)
    if result.returncode:
        raise RuntimeError('Validation command failed; exit='+str(result.returncode)+'; '+summarize(result.stderr))
    return result.stdout


def compose_environment(path):
    """Do not let an operator's exported deployment settings select test data."""
    path=Path(path)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise RuntimeError('Validation settings must not traverse symlinks')
    values={}
    for line in path.read_text().splitlines():
        key,separator,value=line.partition('=')
        if not separator or key not in VALIDATION_KEYS or key in values:
            raise RuntimeError('Unexpected or duplicate validation setting')
        values[key]=value
    if set(values)!=VALIDATION_KEYS or values['WEB_BIND_IP']!='127.0.0.1':
        raise RuntimeError('Complete loopback-only validation settings are required')
    private=path.parent.parent.resolve()
    for key in ('DB_DATA_DIR','MEDIA_DATA_DIR','BACKUP_DATA_DIR'):
        directory=Path(values[key])
        if (not directory.is_absolute() or directory.is_symlink()
                or any(p.is_symlink() for p in directory.parents)
                or not directory.is_dir() or private not in directory.resolve().parents):
            raise RuntimeError('Validation data must stay inside the new private test directory')
    # An explicit --env-file has lower precedence than the process environment.
    # Keep only OS/validated local-Docker transport settings, then supply every
    # application interpolation value ourselves. COMPOSE_* settings never enter.
    result={k:v for k,v in os.environ.items() if k in PROCESS_ENV_KEYS}
    result.update(VALIDATION_DEFAULTS)
    result.update(values)
    return result


def require_validation_project(project):
    if not re.fullmatch(r'lj-(?:install|restore)-[0-9a-f]{10}',project):
        raise RuntimeError('Only this validation project namespace is accepted')


def require_unused_project(project):
    require_validation_project(project)
    if run('docker','ps','--all','--filter','label=com.docker.compose.project='+project,'--format','{{.ID}}').strip():
        raise RuntimeError('Validation project already has containers; nothing started or stopped')


def compose(project,env,*args,override=None):
    require_validation_project(project)
    cmd=['docker','compose','--project-name',project,'--env-file',str(env),'-f',str(ROOT/'compose.yaml')]
    if override:cmd+=['-f',str(override)]
    return run(*cmd,*args,env=compose_environment(env))


def stop_projects(projects):
    failures=0
    for name,configuration,override in reversed(projects):
        try:compose(name,configuration,'stop',override=override)
        except Exception:
            failures+=1
            print('Validation container stop failed; no data or images deleted',file=sys.stderr)
    if failures:
        raise RuntimeError('Validation cleanup incomplete; success was not recorded')


def client(project,env):
    port=int(compose(project,env,'port','web','80').strip().rsplit(':',1)[1])
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def request(path,data=None,headers=None):
        req=urllib.request.Request('http://127.0.0.1:'+str(port)+path,
            data=None if data is None else json.dumps(data).encode(),
            headers=({'Content-Type':'application/json'} if data is not None else {})|(headers or {}))
        with opener.open(req,timeout=15) as response:
            body=response.read()
            return json.loads(body) if 'application/json' in response.headers.get('Content-Type','') else body
    return request


def login(request,password):
    token=request('/api/auth/csrf')['csrf_token']
    request('/api/auth/login',{'username':'synthetic-install','password':password},{'x-csrf-token':token})
    assert request('/api/auth/me')['username']=='synthetic-install'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-tag',required=True)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise SystemExit('Validation report already exists; nothing overwritten')
    host=os.getenv('DOCKER_HOST','')
    if host and not host.startswith(('unix://','npipe://')):raise SystemExit('Local Docker only')
    endpoint=json.loads(run('docker','context','inspect','--format','{{json .Endpoints.docker.Host}}'))
    if not endpoint.startswith(('unix://','npipe://')):raise SystemExit('Local Docker context required')
    run('docker','image','inspect','life-journal:'+args.image_tag)
    run('docker','image','inspect','postgres:17-alpine')
    private=Path(tempfile.mkdtemp(prefix='lj-install-',dir=os.getenv('RUNNER_TEMP',tempfile.gettempdir())))
    suffix=secrets.token_hex(5);project='lj-install-'+suffix;restore='lj-restore-'+suffix
    password=secrets.token_urlsafe(30);key=secrets.token_urlsafe(36)
    def environment(name,**extra):
        base=private/name;base.mkdir()
        for directory in ('postgres','media','backups'):(base/directory).mkdir()
        values={'POSTGRES_DB':'lj_validation','POSTGRES_USER':'lj_validation',
            'POSTGRES_PASSWORD':password,'SETUP_KEY':key,'COOKIE_SECURE':'false',
            'IMAGE_TAG':args.image_tag,'POSTGRES_IMAGE':'postgres:17-alpine','WEB_BIND_IP':'127.0.0.1','WEB_PORT':'0',
            'DB_DATA_DIR':str(base/'postgres'),'MEDIA_DATA_DIR':str(base/'media'),'BACKUP_DATA_DIR':str(base/'backups')}
        values.update(extra);env=base/'.env';env.write_text(''.join(k+'='+v+'\n' for k,v in values.items()));env.chmod(0o600)
        return env,base
    env,base=environment('install');restore_env,restore_base=environment('restore',BACKUP_DATA_DIR=str(base/'backups'))
    restore_override=private/'restore.yaml'
    restore_override.write_text(json.dumps({'services':{'maintenance':{'volumes':[
        str(base/'backups')+':/backups:ro',str(restore_base/'media')+':/data/media:rw']}}}))
    started=[]
    validation_complete=False
    try:
        require_unused_project(project)
        require_unused_project(restore)
        compose(project,env,'config','--quiet')
        started.append((project,env,None))
        compose(project,env,'up','-d','--pull','never','--wait','--wait-timeout','240')
        request=client(project,env)
        assert request('/api/health')['ok'] is True
        assert b'<html' in request('/').lower()
        assert request('/api/setup/status')['required'] is True
        csrf=request('/api/auth/csrf')['csrf_token']
        request('/api/setup/complete',{'username':'synthetic-install','password':password,'title':'Synthetic installation'},
            {'Authorization':'Bearer '+key,'x-csrf-token':csrf})
        login(request,password)
        compose(project,env,'restart')
        compose(project,env,'up','-d','--pull','never','--wait','--wait-timeout','240')
        request=client(project,env);login(request,password)
        assert request('/api/setup/status')['required'] is False
        # Supply the existing probe as code; only the runner's synthetic service
        # is used. No additional host directory is mounted for this check.
        probe=(ROOT/'tests/lgpl_replacement_probe.py').read_text()
        lgpl=json.loads(compose(project,env,'exec','--user','10001:10001','-T',
            '-e','RUN_LJ_LGPL_REPLACEMENT_DRILL=1','maintenance',
            'python','-c',probe).strip().splitlines()[-1])
        backup=json.loads(compose(project,env,'exec','--user','10001:10001','-T','maintenance','python','-m','app.backup','create').strip().splitlines()[-1])
        backup_id=backup['id']
        compose(project,env,'exec','--user','10001:10001','-T','maintenance','python','-m','app.backup','verify','--id',backup_id)
        started.append((restore,restore_env,restore_override))
        compose(restore,restore_env,'up','-d','--pull','never','--wait','--wait-timeout','120','db',override=restore_override)
        # Use the existing empty-directory initializer, without starting API or
        # initializing the restore database. Never chown populated user data.
        compose(restore,restore_env,'run','--rm','--no-deps','-e','CONTAINER_ROLE=api',
            'maintenance','python','-c','pass',override=restore_override)
        output=compose(restore,restore_env,'run','--rm','--no-deps','maintenance','python','-m','app.backup','restore',
            '--id',backup_id,'--confirm-empty-target',override=restore_override)
        restored=json.loads(output.strip().splitlines()[-1]);assert restored['database_restore']=='passed' and restored['media_restore']=='passed'
        compose(restore,restore_env,'up','-d','--pull','never','--wait','--wait-timeout','240',override=restore_override)
        restored_request=client(restore,restore_env);login(restored_request,password)
        upgrade_name='lj_validation_upgrade_'+suffix
        compose(project,env,'exec','-T','db','createdb','-U','lj_validation',upgrade_name)
        for directory in ('upgrade-media','upgrade-backups'):(private/directory).mkdir()
        upgrade_override=private/'upgrade.yaml'
        upgrade_override.write_text(json.dumps({'services':{'maintenance':{'environment':{
            'POSTGRES_DB':upgrade_name,'RUN_LJ_SYNTHETIC_UPGRADE_DRILL':'1'},'volumes':[
                str(private/'upgrade-media')+':/data/media:rw',str(private/'upgrade-backups')+':/backups:rw',str(ROOT/'tests')+':/validation:ro']}}}))
        compose(project,env,'run','--rm','--no-deps','-e','CONTAINER_ROLE=api',
            'maintenance','python','-c','pass',override=upgrade_override)
        upgrade_output=compose(project,env,'run','--rm','--no-deps','maintenance','python','/validation/synthetic_upgrade_probe.py',override=upgrade_override)
        upgrade=json.loads(upgrade_output.strip().splitlines()[-1])
        report={'four_container_health':'passed','api_health_http_200':True,'web_static_and_proxy':'passed',
            'initial_setup_and_login':'passed','restart_and_database_persistence':'passed',
            'ordinary_backup_and_independent_restore':'passed','restored_login':'passed','synthetic_upgrade':upgrade,
            'lgpl_replacement':lgpl,
            'production_or_nas_accessed':False,'image_tag':args.image_tag}
        validation_complete=True
    finally:
        if validation_complete:
            stop_projects(started)
        else:
            # Preserve the primary validation error, but attempt every owned
            # project and report cleanup failure without turning either green.
            try:stop_projects(started)
            except RuntimeError:print('Validation also left cleanup incomplete',file=sys.stderr)
    with args.output.open('x') as stream:stream.write(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
