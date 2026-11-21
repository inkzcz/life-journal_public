"""Build and deliver only the business image; PostgreSQL is managed by the NAS.
Never push, delete or replace an existing conflicting image. Tools are stdlib only.
"""
import json,shutil
from pathlib import Path
from scripts import release as legacy,unified_release as layout


def enabled(version,root):
    import re
    value=(root/'VERSION').read_text().strip() if legacy.SHA.fullmatch(version) else version.removeprefix('v')
    match=re.match(r'^(\d+)\.(\d+)\.(\d+)',value)
    return bool(match and tuple(map(int,match.groups()))>=(5,1,6))


def build(commands,revision,version,root):
    from scripts import local_images as local
    local.build_tag(version,root)
    app=local.inspect(commands,layout.image('app')+':'+version)
    if app is not None:local.validate_image(app,revision,version,getattr(commands,'source_identity',None))
    if app is None:
        source=getattr(commands,'source_identity',None)
        extra=[] if source is None else ['--label','io.life-journal.revision-verified='+str(source['revision_verified']).lower(),'--label','io.life-journal.build-identity='+source['build_identity']]
        if source is not None and not source['revision_verified']:extra+=['--label','io.life-journal.zip-tree='+source['source_tree_sha256']]
        commands.build('docker','buildx','build','--load','--provenance=false','--sbom=false','--platform','linux/amd64','--build-arg','APP_VERSION='+(source['build_identity'] if source else revision),'--build-arg','BUILD_INFO='+json.dumps(local.build_metadata(revision,source),separators=(',',':')),'--label','org.opencontainers.image.revision='+revision,'--label','org.opencontainers.image.version='+version,'--label','org.opencontainers.image.source=https://github.com/inkzcz/life-journal_public',*extra,'-f',str(root/'Dockerfile'),'-t',layout.image('app')+':'+version,str(root))
        local.validate_image(local.inspect(commands,layout.image('app')+':'+version),revision,version,source)


def export(commands,revision,version,destination,root):
    from scripts import local_images as local
    app=local.inspect(commands,layout.image('app')+':'+version)
    local.validate_image(app,revision,version,getattr(commands,'source_identity',None))
    target=Path(destination).absolute()
    if target.exists() or target.is_symlink():raise ValueError('Output directory exists; nothing overwritten')
    if not target.parent.is_dir():raise ValueError('Create the output parent directory first')
    if shutil.disk_usage(target.parent).free<app['Size']*1.2+64*1024**2:raise ValueError('Insufficient free space for one business TAR')
    target.mkdir();files={}
    for component in layout.COMPONENTS:
        name,checksum=layout.names(component,version);partial=target/(name+'.partial')
        commands.run('docker','save','-o',str(partial),layout.image(component)+':'+version)
        partial.rename(target/name);files[name]=legacy.digest(target/name)
        (target/checksum).write_bytes((files[name]+'  '+name+'\n').encode('ascii'))
    # The directory is still a private staging directory; no completion manifest.
    evidence={'format':'life-journal-local-images-v1','revision':revision,'version':version,'platform':'linux/amd64','source':getattr(commands,'source_identity',None),'files':files}
    (target/'images.json').write_text(json.dumps(evidence,indent=2))
    configs=layout.verify_bundle(target,revision,version,commands)
    evidence['config_digests']=configs
    (target/'images.json').write_text(json.dumps(evidence,indent=2))
