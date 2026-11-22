"""Synthetic released-v5.1.9 -> candidate upgrade; no production access or downgrade.

Uses the existing strict Compose environment/mount/project/cleanup guards. Only
the exact published old TAR is accepted; the database and media live in a new
private RUNNER_TEMP directory. This does not reproduce UPGRADE-001.
"""
import argparse
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import struct
import sys
import tarfile
import tempfile
import urllib.request
import uuid
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parent))
from docker_installation import ROOT, compose, require_unused_project, run, stop_projects

OLD_TAG='v5.1.9'
OLD_SOURCE='2db730b1bad683e5056f3f096987074bdfe5e02a'
OLD_TAR_SHA256='e7b429fcb5103cc32e6f246ec3b57550f15ed893f9863cf10ac5ecad6ba120eb'


def verify_previous_tar(path):
    path=path.resolve(strict=True)
    with path.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=OLD_TAR_SHA256:
            raise ValueError('Previous published TAR checksum mismatch')
    with tarfile.open(path) as archive:
        images=json.load(archive.extractfile('manifest.json'))
        if len(images)!=1 or images[0]['RepoTags']!=['life-journal:'+OLD_TAG]:
            raise ValueError('Previous TAR is not the sole released business image')
        raw=archive.extractfile(images[0]['Config']).read();config=json.loads(raw)
        labels=config['config']['Labels']
        if (config['os']!='linux' or config['architecture']!='amd64'
                or labels.get('org.opencontainers.image.revision')!=OLD_SOURCE
                or labels.get('org.opencontainers.image.version')!=OLD_TAG):
            raise ValueError('Previous image identity mismatch')
    return 'sha256:'+hashlib.sha256(raw).hexdigest()


def synthetic_png():
    def chunk(name,data):
        return struct.pack('!I',len(data))+name+data+struct.pack('!I',zlib.crc32(name+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',8,8,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x80\x99\x88'*8)*8))+chunk(b'IEND',b'')


def api(project,env):
    port=int(compose(project,env,'port','web','80').strip().rsplit(':',1)[1])
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def request(path,data=None,method=None,content_type=None,extra_headers=None):
        headers=dict(extra_headers or {})
        if data is not None:
            headers['x-csrf-token']=request('/api/auth/csrf')['csrf_token']
            headers['Content-Type']=content_type or 'application/json'
        body=data if isinstance(data,bytes) else json.dumps(data).encode() if data is not None else None
        with opener.open(urllib.request.Request('http://127.0.0.1:'+str(port)+path,data=body,headers=headers,method=method),timeout=20) as response:
            raw=response.read()
            return json.loads(raw) if 'application/json' in response.headers.get('Content-Type','') else raw
    return request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-tag',required=True)
    parser.add_argument('--previous-tar',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists() or args.output.is_symlink():raise ValueError('Fresh report path required')
    if not re.fullmatch(r'v5\.1\.10-candidate\.[0-9a-f]{7,40}',args.image_tag):raise ValueError('Only the v5.1.10 development candidate is accepted')
    host=os.getenv('DOCKER_HOST','')
    if host and not host.startswith(('unix://','npipe://')):raise ValueError('Local Docker only')
    endpoint=json.loads(run('docker','context','inspect','--format','{{json .Endpoints.docker.Host}}'))
    if not endpoint.startswith(('unix://','npipe://')):raise ValueError('Local Docker context required')
    expected=verify_previous_tar(args.previous_tar)
    ids=run('docker','image','ls','--filter','reference=life-journal:'+OLD_TAG,'--no-trunc','--format','{{.ID}}').split()
    if ids and ids!=[expected]:raise ValueError('Conflicting previous image; nothing overwritten or removed')
    run('docker','load','--input',str(args.previous_tar))
    if json.loads(run('docker','image','inspect','life-journal:'+OLD_TAG))[0]['Id']!=expected:raise ValueError('Loaded previous image mismatch')
    run('docker','image','inspect','life-journal:'+args.image_tag)
    run('docker','image','inspect','postgres:17-alpine')
    private=Path(tempfile.mkdtemp(prefix='lj-version-upgrade-',dir=os.getenv('RUNNER_TEMP',tempfile.gettempdir())))
    base=private/'install';base.mkdir()
    for name in ('postgres','media','backups'):(base/name).mkdir()
    password=secrets.token_urlsafe(30);setup=secrets.token_urlsafe(36)
    values={'POSTGRES_DB':'lj_validation','POSTGRES_USER':'lj_validation','POSTGRES_PASSWORD':password,
        'SETUP_KEY':setup,'COOKIE_SECURE':'false','IMAGE_TAG':OLD_TAG,'POSTGRES_IMAGE':'postgres:17-alpine',
        'WEB_BIND_IP':'127.0.0.1','WEB_PORT':'0','DB_DATA_DIR':str(base/'postgres'),
        'MEDIA_DATA_DIR':str(base/'media'),'BACKUP_DATA_DIR':str(base/'backups')}
    env=base/'.env'
    def write_settings():
        env.write_text(''.join(k+'='+v+'\n' for k,v in values.items()));env.chmod(0o600)
    write_settings()
    project='lj-install-'+secrets.token_hex(5)
    started=[]
    try:
        require_unused_project(project);compose(project,env,'config','--quiet')
        started.append((project,env,None))
        compose(project,env,'up','-d','--pull','never','--wait','--wait-timeout','240')
        request=api(project,env)
        # Use the same cookie jar and CSRF-protected endpoint, without printing credentials.
        request('/api/setup/complete',{'username':'synthetic-install','password':password,'title':'Synthetic version upgrade'},
                extra_headers={'Authorization':'Bearer '+setup})
        request('/api/auth/login',{'username':'synthetic-install','password':password})
        t=request('/api/admin/content/types',{'slug':'synthetic-upgrade-'+secrets.token_hex(5),'name':'合成旧类型',
            'fields':[{'kind':'short_text','name':'保留的旧字段','position':0}]})
        boundary='synthetic-'+secrets.token_hex(12)
        data=('--'+boundary+'\r\nContent-Disposition: form-data; name="file"; filename="synthetic.png"\r\nContent-Type: image/png\r\n\r\n').encode()+synthetic_png()+('\r\n--'+boundary+'--\r\n').encode()
        media=request('/api/admin/archive/media',data,content_type='multipart/form-data; boundary='+boundary)
        card={'id':str(uuid.uuid4()),'kind':'m','name':'合成旧电影','fields':{'review':'原评价'},'media_ids':[media['id']]}
        payload={'type_id':t['id'],'schema_version':t['revision'],'title':'合成 v5.1.9 文章','body_format':2,'marker_version':2,
            'body':'原正文\n\n:::lj-entry-v1\n'+json.dumps(card,ensure_ascii=False)+'\n:::\n','display_date':'2026-11-22',
            'status':'draft','values':{t['fields'][0]['id']:'原动态字段值'},'article':{'travel_enabled':True},
            'connections':{'media':[{'id':media['id'],'cover':True,'caption':'合成照片'}],'places':[],'links':[]},
            'life':{'start_date':'2026-11-22','end_date':'2026-11-22','activities':[{'id':str(uuid.uuid4()),'day':'2026-11-22','title':'原行程','media_ids':[media['id']]}]}}
        original=request('/api/admin/content/records',payload)
        backup=json.loads(compose(project,env,'exec','--user','10001:10001','-T','maintenance','python','-m','app.backup','create').strip().splitlines()[-1])
        compose(project,env,'exec','--user','10001:10001','-T','maintenance','python','-m','app.backup','verify','--id',backup['id'])
        before=compose(project,env,'exec','-T','db','psql','-U','lj_validation','-d','lj_validation','-Atc','SELECT version_num FROM alembic_version').strip()
        assert before=='0021_anniversary_calendar'
        compose(project,env,'stop','web','api','maintenance')
        values['IMAGE_TAG']=args.image_tag;write_settings()
        compose(project,env,'up','-d','--pull','never','--wait','--wait-timeout','240')
        request=api(project,env);request('/api/auth/login',{'username':'synthetic-install','password':password})
        upgraded=request('/api/admin/content/records/'+original['id'])
        for key in ('id','type_id','schema_version','body','values','life','article','connections'):
            assert upgraded[key]==original[key],key
        assert request('/api/library-media/'+media['id']+'/original')==synthetic_png()
        default=request('/api/admin/content/types/default-article',{})
        assert default['fields']==[] and default['active'] is True
        for enabled in (False,True):
            update={k:v for k,v in payload.items() if k!='type_id'}
            update['expected_revision']=upgraded['revision'];update['article']={'travel_enabled':enabled}
            upgraded=request('/api/admin/content/records/'+original['id'],update,method='PUT')
            for key in ('body','values','life','connections'):assert upgraded[key]==original[key],key
            assert upgraded['article']['travel_enabled'] is enabled
        compose(project,env,'restart');compose(project,env,'up','-d','--pull','never','--wait','--wait-timeout','240')
        request=api(project,env);request('/api/auth/login',{'username':'synthetic-install','password':password})
        assert request('/api/admin/content/records/'+original['id'])['body']==original['body']
        after=compose(project,env,'exec','-T','db','psql','-U','lj_validation','-d','lj_validation','-Atc','SELECT version_num FROM alembic_version').strip()
        assert after==before
    finally:
        stop_projects(started)
    report={'synthetic_same_schema_upgrade':'passed','from_version':'5.1.9','to_version':'5.1.10',
        'old_business_tar_sha256':OLD_TAR_SHA256,'schema_before':before,'schema_after':after,
        'old_backup_created_and_verified':True,'existing_article_fields_cards_media_itinerary':'preserved',
        'new_default_type_and_travel_toggles':'passed','candidate_restart_persistence':'passed',
        'production_or_nas_accessed':False,'UPGRADE-001':'Not reproduced or claimed fixed'}
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
