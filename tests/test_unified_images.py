"""Small synthetic manifests exercise fail-closed logic, NOT real-image evidence."""
import copy,hashlib,json,subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import unified_images as images,unified_release as layout,local_images
REV='a'*40
VER='v5.1.7'

def raw_manifest(config='sha256:'+'b'*64):
    raw=json.dumps({'schemaVersion':2,'config':{'digest':config},'layers':[]},separators=(',',':'))
    return raw,'sha256:'+hashlib.sha256(raw.encode()).hexdigest()

class Commands:
    def __init__(self,existing=None):self.existing=existing or {};self.calls=[];self.builds=[]
    def run(self,*args):
        self.calls.append(args)
        if 'imagetools' in args:raise AssertionError('Registry access forbidden')
        if args[:3]==('docker','image','inspect'):
            ref=args[-1]
            if ref not in self.existing:raise subprocess.CalledProcessError(1,args,stderr='No such image')
            return json.dumps([self.existing[ref]])
        raise AssertionError(args)
    def build(self,*args):self.builds.append(args);raise AssertionError('Unexpected build')


def app_image():return {'Architecture':'amd64','Os':'linux','Config':{'Labels':{'org.opencontainers.image.revision':REV,'org.opencontainers.image.version':VER,'org.opencontainers.image.source':'https://github.com/inkzcz/life-journal_public'}}}
def db_image():return {'Architecture':'amd64','Os':'linux','Id':'sha256:'+'b'*64}

def test_layout_is_versioned_without_changing_historical_exports(tmp_path):
    (tmp_path/'VERSION').write_text('5.1.7')
    assert images.enabled(VER,tmp_path) and images.enabled(REV,tmp_path)
    assert not images.enabled('v5.1.5',tmp_path)
    assert layout.COMPONENTS==('app',)
    assert layout.image('app')=='life-journal'
    with pytest.raises(ValueError):layout.image('postgres')
    assert layout.names('app',VER)[0]=='life-journal-app-v5.1.7-amd64.tar'
    from scripts import release
    assert release.COMPONENTS==('web','api','maintenance')


def test_app_conflict_stops_before_any_database_network_or_build(tmp_path):
    (tmp_path/'VERSION').write_text('5.1.7');bad=app_image();bad['Architecture']='arm64';transport=Commands({'life-journal:'+VER:bad})
    with pytest.raises(ValueError,match='conflicts'):images.build(transport,REV,VER,tmp_path)
    assert not transport.builds
    assert all(call[:3]==('docker','image','inspect') for call in transport.calls)


def test_matching_app_never_touches_database_even_when_database_tag_conflicts(tmp_path):
    (tmp_path/'VERSION').write_text('5.1.7')
    transport=Commands({'life-journal:'+VER:app_image(),'life-journal-postgres:'+VER:{'Id':'conflict'}})
    images.build(transport,REV,VER,tmp_path)
    assert transport.calls==[('docker','image','inspect','life-journal:'+VER)]
    assert not transport.builds and not hasattr(transport,'database_source')


@pytest.fixture
def archives(tmp_path):
    import io,tarfile
    seed=tmp_path/'seed';seed.mkdir();configs={};ids={}
    def save(component,env):
        config={'architecture':'amd64','os':'linux','config':{'Env':env},'rootfs':{'type':'layers','diff_ids':[]}}
        if component=='app':config['config']['Labels']=app_image()['Config']['Labels']
        data=json.dumps(config,separators=(',',':')).encode();digest='sha256:'+hashlib.sha256(data).hexdigest();name=layout.names(component,VER)[0]
        manifest=[{'Config':'config.json','RepoTags':[layout.image(component)+':'+VER],'Layers':[]}]
        with tarfile.open(seed/name,'w') as archive:
            for path,raw in [('config.json',data),('manifest.json',json.dumps(manifest).encode())]:
                info=tarfile.TarInfo(path);info.size=len(raw);archive.addfile(info,io.BytesIO(raw))
        configs[component]=config;ids[component]=digest
        return digest
    save('app',[])
    class ArchiveCommands(Commands):
        def __init__(self):super().__init__();self.loads=0
        def run(self,*args):
            self.calls.append(args)
            if args[:5]==('docker','buildx','imagetools','inspect','--raw'):raise AssertionError("Registry access forbidden")
            if args[:2]==('docker','load'):
                self.loads+=1
                with tarfile.open(args[-1]) as archive:
                    m=json.load(archive.extractfile('manifest.json'))[0];data=archive.extractfile(m['Config']).read();c=json.loads(data)
                self.existing[m['RepoTags'][0]]={'Id':'sha256:'+hashlib.sha256(data).hexdigest(),'Architecture':c['architecture'],'Os':c['os'],'Config':c['config'],'RootFS':{'Layers':c['rootfs']['diff_ids']},'Size':1024}
                return ''
            if args[:3]==('docker','image','ls'):return '\n'.join(sorted(key for key in self.existing if key.rsplit(':',1)[0]==args[-1]))
            if args[:2]==('docker','save'):
                import shutil
                component=next(c for c in layout.COMPONENTS if args[-1]==layout.image(c)+':'+VER)
                shutil.copyfile(seed/layout.names(component,VER)[0],args[3]);return ''
            if args[:3]==('docker','image','inspect'):
                if args[-1] not in self.existing:raise subprocess.CalledProcessError(1,args,stderr='No such image')
                return json.dumps([self.existing[args[-1]]])
            raise AssertionError(args)
    transport=ArchiveCommands()
    for component in layout.COMPONENTS:
        transport.existing[layout.image(component)+':'+VER]={'Id':ids[component],'Architecture':'amd64','Os':'linux','Config':configs[component]['config'],'RootFS':{'Layers':[]},'Size':1024}
    return seed,None,transport


def test_single_archive_export_checks_hashes_and_repeated_load_sequence(archives,tmp_path):
    # Commands are emulated here; actual docker load is required by the CI probe.
    seed,pin,transport=archives;target=tmp_path/'delivery'
    images.export(transport,REV,VER,target,tmp_path)
    evidence=json.loads((target/'images.json').read_text())
    assert len(list(target.glob('*.tar')))==1 and set(evidence['config_digests'])=={'app'}
    assert 'database_source' not in evidence and transport.loads==2
    assert not any('postgres' in ' '.join(call) or 'imagetools' in call or 'pull' in call or 'tag' in call for call in transport.calls)
    for name,digest in evidence['files'].items():assert (target/(name+'.sha256')).read_text()==digest+'  '+name+'\n'
    assert not any(call[:2]==('docker','push') for call in transport.calls)
    with pytest.raises(ValueError,match='exists'):images.export(transport,REV,VER,target,tmp_path)


def test_failed_second_export_never_produces_a_complete_package_or_deletes_images(archives,tmp_path):
    seed,pin,transport=archives;original=transport.run
    def fail(*args):
        if args[:2]==('docker','save') :raise RuntimeError('synthetic interrupted export')
        return original(*args)
    transport.run=fail;before=copy.deepcopy(transport.existing);target=tmp_path/'partial'
    with pytest.raises(RuntimeError,match='interrupted'):images.export(transport,REV,VER,target,tmp_path)
    assert not (target/'manifest.json').exists() and not (target/'images.json').exists()
    assert transport.existing==before and transport.loads==0


def test_source_identity_checks_the_only_application_archive(archives):
    from scripts import release_local
    seed,_,_=archives
    with pytest.raises(ValueError):release_local.verify_bundle_source(seed,{'version':VER,'source':{'revision':'b'*40}})


def test_business_dockerfile_never_resolves_a_postgres_image():
    dockerfile=(Path(__file__).parents[1]/'Dockerfile').read_text()
    assert 'FROM postgres' not in dockerfile and '--from=postgres' not in dockerfile
    assert 'postgresql-client-17' in dockerfile and 'postgresql-17' in dockerfile


def test_proxy_ca_is_readable_by_unprivileged_apt_without_entering_image_layers():
    dockerfile=(Path(__file__).parents[1]/'Dockerfile').read_text()
    apt_step=dockerfile[dockerfile.index('# The CA bundle'):dockerfile.index('ENV PATH=/opt/venv')]
    assert 'id=build_ca,mode=0444' in apt_step
    assert 'Acquire::https::CaInfo' in apt_step
    assert 'COPY /run/secrets' not in dockerfile
    assert 'Verify-Peer "false"' not in dockerfile
