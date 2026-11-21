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
import secrets
import subprocess
import sys
import tempfile
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.command_errors import summarize

ROOT=Path(__file__).resolve().parents[1]


def run(*args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=360)
    if result.returncode:
        raise RuntimeError('Validation command failed; exit='+str(result.returncode)+'; '+summarize(result.stderr))
    return result.stdout


def compose(project,env,*args,override=None):
    cmd=['docker','compose','--project-name',project,'--env-file',str(env),'-f',str(ROOT/'compose.yaml')]
    if override:cmd+=['-f',str(override)]
    return run(*cmd,*args)


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
    try:
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
        backup=json.loads(compose(project,env,'exec','-T','maintenance','python','-m','app.backup','create').strip().splitlines()[-1])
        backup_id=backup['id']
        compose(project,env,'exec','-T','maintenance','python','-m','app.backup','verify','--id',backup_id)
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
            'production_or_nas_accessed':False,'image_tag':args.image_tag}
        args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    finally:
        for name,configuration,override in reversed(started):
            try:compose(name,configuration,'stop',override=override)
            except Exception:print('Validation container stop failed; no data or images deleted',file=sys.stderr)


if __name__=='__main__':main()
