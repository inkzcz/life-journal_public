"""Atomic local delivery wrapper. No GitHub/GHCR login, push, or data cleanup."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import uuid
sys.dont_write_bytecode=True
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import local_images as images,release
from scripts.source_identity import identify
from scripts.release_source import verify_source
ROOT=images.ROOT
TOOL_VERSION='5.1.11'

def package_layout(version):
    from scripts import unified_images,unified_release
    return unified_release if unified_images.enabled(version,ROOT) else release



def no_links(path):
    path=Path(os.path.abspath(path))
    for p in [path,*path.parents]:
        if p.is_symlink() or (p.exists() and getattr(p.stat(),'st_file_attributes',0)&0x400):
            raise ValueError('Output must not traverse symlinks/junctions')
    return path


def existing_bundle(path,version):
    release=package_layout(version)
    no_links(path)
    for file in path.iterdir():
        if not no_links(file).is_file():raise ValueError('Bundle contains non-regular files')
    m=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
    if not isinstance(m,dict):raise ValueError('Manifest must be an object')
    if m.get('format')!='life-journal-local-release-v1' or m.get('version')!=version:raise ValueError('Refusing to replace an unrecognized directory')
    expected={'manifest.json','images.json','SHA256SUMS.txt'}
    for c in release.COMPONENTS:expected.update(release.names(c,version))
    if {p.name for p in path.iterdir()}!=expected:raise ValueError('Existing directory contains unexpected files; nothing moved')
    if not isinstance(m.get('source'),dict) or not isinstance(m.get('images'),dict) or not isinstance(m.get('tar_sha256'),dict):raise ValueError('Invalid manifest fields')
    if type(m['source'].get('revision_verified')) is not bool or m.get('registry_published') is not False:raise ValueError('Invalid source/publication declaration')
    files=m['tar_sha256']
    if set(files)!={release.names(c,version)[0] for c in release.COMPONENTS}:raise ValueError('Incomplete existing release')
    for name,digest in files.items():
        if release.digest(path/name)!=digest or (path/(name+'.sha256')).read_text()!=digest+'  '+name+'\n':raise ValueError('Existing bundle integrity mismatch')
    if (path/'SHA256SUMS.txt').read_text()!=''.join(f'{files[n]}  {n}\n' for n in sorted(files)):raise ValueError('Unified checksums differ')
    evidence=json.loads((path/'images.json').read_text())
    if not isinstance(evidence,dict):raise ValueError('Image evidence must be an object')
    if evidence.get('files')!=files or evidence.get('version')!=version or evidence.get('revision')!=m['source']['revision'] or evidence.get('source')!=m['source'] or evidence.get('platform')!='linux/amd64':raise ValueError('Manifest source/content differs')
    for c in release.COMPONENTS:
        if m['images'][c]!={'name':release.image(c)+':'+version,'config_digest':evidence['config_digests'][c],'tar':release.names(c,version)[0]}:raise ValueError('Manifest image identity differs')
    return m



def preflight(commands,output):
    for name in ['backend/Dockerfile','backend/Dockerfile.maintenance','frontend/Dockerfile','backend/app','backend/alembic','frontend/src']:
        if not (ROOT/name).exists():raise ValueError('Missing build input: '+name)
    if not shutil.which('docker'):raise ValueError('Docker not found; install/start Docker Desktop in Linux-container mode')
    images.check_product_version(ROOT)
    commands.context=images.local_context(commands)
    if commands.run('docker','info','--format','{{.OSType}}').strip()!='linux':raise ValueError('Docker must use Linux containers')
    commands.run('docker','buildx','version')
    platform=commands.run('docker','buildx','inspect',commands.context,'--bootstrap')
    if 'linux/amd64' not in platform:raise ValueError('Local builder does not support linux/amd64')
    if shutil.disk_usage(output).free<1024**3:raise ValueError('Less than 1 GiB free; build/export needs additional image-dependent space')


def deliver(version,revision=None,output=None,force=False,commands=None,verification="auto"):
    release=package_layout(version)
    if not release.VERSION.fullmatch(version):raise ValueError('Version must be vMAJOR.MINOR.PATCH[-prerelease]')
    images.build_tag(version,ROOT)
    proof=verify_source(ROOT,revision,verification)
    source=proof.identity
    release.validate_inputs(source['revision'],version)
    parent=no_links(output or ROOT/'release')
    if parent in {ROOT,Path(parent.anchor),Path.home()} or any(p in {ROOT/'backend',ROOT/'frontend',ROOT/'.git'} for p in [parent,*parent.parents]):raise ValueError('Output cannot be the source root or inside a build context')
    parent.mkdir(parents=True,exist_ok=True);destination=parent/version
    no_links(destination)
    if destination.exists() and not force:raise ValueError('Version directory exists; choose a new version or --force (previous bundle retained)')
    before=existing_bundle(destination,version) if destination.exists() else None
    commands=commands or images.Docker();commands.source_identity=source
    preflight(commands,parent)
    with images.local_lock(version):
        probe=parent/('.write-probe-'+uuid.uuid4().hex)
        with probe.open('x'):pass
        probe.unlink()
        print('[1/4] 源码内容验证通过：'+source['revision']+'；Git HEAD verified='+str(source['revision_verified'])+'；source_verified='+str(source.get('source_verified',False)),flush=True)
        print('[2/4] Building '+str(len(release.COMPONENTS))+' local linux/amd64 delivery images (no Registry push)',flush=True)
        images.build(commands,source['revision'],version)
        # Detect edited inputs before creating a successful package.
        proof.recheck()
        stage=parent/('.'+version+'.partial.'+uuid.uuid4().hex)
        print('[3/4] Export, SHA256, config identity and two docker loads',flush=True)
        images.export(commands,source['revision'],version,stage)
        evidence=json.loads((stage/'images.json').read_text())
        sums=evidence['files']
        if len(sums)!=len(release.COMPONENTS) or any((stage/n).stat().st_size==0 for n in sums):raise ValueError('Empty/incomplete TAR output')
        (stage/'SHA256SUMS.txt').write_bytes(''.join(f'{sums[n]}  {n}\n' for n in sorted(sums)).encode('ascii'))
        manifest={'format':'life-journal-local-release-v1','version':version,'built_at':datetime.now(timezone.utc).isoformat(),'platform':'linux/amd64','source':source,'tool_version':TOOL_VERSION,'tool_script_sha256':release.digest(Path(__file__)),'tar_sha256':sums,'images':{c:{'name':release.image(c)+':'+version,'config_digest':evidence['config_digests'][c],'tar':release.names(c,version)[0]} for c in release.COMPONENTS},'registry_published':False}
        (stage/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        existing_bundle(stage,version)
        proof.recheck()
        if destination.exists():
            if not force or existing_bundle(destination,version)!=before:raise ValueError('Output changed concurrently; nothing overwritten')
            previous=parent/('.'+version+'.previous.'+uuid.uuid4().hex)
            destination.rename(previous);print('Previous bundle retained: '+str(previous),flush=True)
        stage.rename(destination)
        print('[4/4] Local TAR release verified: '+str(destination),flush=True)
        print('SHA256SUMS.txt and manifest.json verified; NOT a GHCR/GitHub release',flush=True)
        return destination


def verify_bundle_source(path,manifest):
    release=package_layout(manifest['version'])
    # User-editable JSON must agree with the bytes in every image config.
    for component in release.COMPONENTS:
        with tarfile.open(path/release.names(component,manifest['version'])[0]) as archive:
            entries=json.load(archive.extractfile('manifest.json'))
            if not isinstance(entries,list) or len(entries)!=1:raise ValueError('Each TAR must contain exactly one image')
            config=json.load(archive.extractfile(entries[0]['Config']))
            if not isinstance(config,dict) or not isinstance(config.get('config'),dict):raise ValueError('Invalid image configuration')
            if not isinstance(config['config'].get('Labels'),dict):raise ValueError('Invalid application labels')
            images.validate_image({'Architecture':config.get('architecture'),'Os':config.get('os'),'Config':{'Labels':config['config']['Labels']}},manifest['source']['revision'],manifest['version'],manifest['source'])


def verify_delivery(path,version,commands=None):
    release=package_layout(version)
    path=no_links(path)
    if path.name!=version:raise ValueError("Only a completed version directory can be verified; partial/previous is not a release")
    m=existing_bundle(path,version)
    release.validate_inputs(m['source']['revision'],version)
    verify_bundle_source(path,m)
    commands=commands or images.Docker()
    commands.context=images.local_context(commands)
    if commands.run('docker','info','--format','{{.OSType}}').strip()!='linux':raise ValueError('Docker must use Linux containers')
    with images.local_lock(version):
        configs=release.verify_bundle(path,m['source']['revision'],version,commands)
        if configs!={c:m['images'][c]['config_digest'] for c in release.COMPONENTS}:raise ValueError('Manifest config identities mismatch')
        print('SHA256, manifest, single-tag TARs and two Docker loads passed; revision_verified='+str(m['source']['revision_verified']),flush=True)
    return m


def discover_source(parent,version):
    parent=no_links(parent)
    candidates=[]
    for root in [parent,*list(parent.iterdir())[:300]]:
        if not root.is_dir() or root.is_symlink():continue
        p=root/'VERSION'
        if p.is_file() and p.stat().st_size<100 and 'v'+p.read_text(encoding='utf-8').strip()==version and (root/'backend/Dockerfile').is_file():candidates.append(root)
    if len(candidates)!=1:raise ValueError('未找到唯一的 '+version+' 源码目录。请将独立启动器放在只有一份官方源码文件夹的目录旁；不要覆盖旧scripts，也可用 -SourceRoot 指定目录。')
    return candidates[0]


def main(argv=None):
    if sys.version_info<(3,10):
        print('Python 3.10+ required',file=sys.stderr);return 1
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path);p.add_argument('--source-parent',type=Path);p.add_argument('--verification',choices=['auto','online','offline'],default='auto')
    p.add_argument('--version');p.add_argument('--revision');p.add_argument('--output-dir',type=Path);p.add_argument('--force',action='store_true');p.add_argument('--verify-only',action='store_true');p.add_argument('--check-source',action='store_true')
    a=p.parse_args(argv)
    try:
        global ROOT
        if a.source_root:ROOT=no_links(a.source_root)
        elif a.source_parent:ROOT=discover_source(a.source_parent,a.version or 'v'+TOOL_VERSION)
        images.ROOT=ROOT
        a.version=a.version or 'v'+(ROOT/'VERSION').read_text(encoding='utf-8').strip()
        if a.check_source:
            images.build_tag(a.version,ROOT)
            proof=verify_source(ROOT,a.revision,a.verification);proof.recheck()
            print(json.dumps(proof.identity,ensure_ascii=False,indent=2));print('源码验证完成；未联系Docker，也未构建或导出镜像。');return 0
        destination=(a.output_dir or ROOT/'release')/a.version
        if a.verify_only or destination.exists() and not a.force:
            if not release.VERSION.fullmatch(a.version):raise ValueError('Invalid version')
            proof=verify_source(ROOT,a.revision,a.verification)
            m=existing_bundle(destination,a.version)
            fields=['revision','revision_verified','build_identity','source_tree_sha256','git_tree_oid']
            if m['source'].get('source_verified') is not True or any(m['source'].get(k)!=proof.identity.get(k) for k in fields):raise ValueError('已有包来源与已验证源码不符或缺少验证证据；旧包保留，请选择其他输出目录')
            verify_delivery(destination,a.version)
            proof.recheck()
            print('完整包已重新校验，无需重建：'+str(destination),flush=True)
        else:deliver(a.version,a.revision,a.output_dir,a.force,verification=a.verification)
    except (ValueError,OSError,KeyError,TypeError,RuntimeError,subprocess.SubprocessError) as e:
        # Never include native stderr wholesale (may contain local config).
        from scripts.command_errors import describe
        message=describe(e)
        translations=[('Docker not found','未找到Docker，请安装并启动Docker Desktop。'),('Docker must use Linux containers','Docker当前不是Linux Containers，请在Docker Desktop切换后重试。'),('Only local Unix sockets','检测到远程Docker地址，已拒绝；只允许本机Docker Desktop，不连接NAS。'),('does not support linux/amd64','当前本地Buildx不支持linux/amd64，请检查Docker Desktop设置。'),('Less than 1 GiB','磁盘可用空间不足1GiB；请使用空间充足的输出盘，本工具不删除旧资源腾空间。'),('Local image conflicts','已有同名镜像的来源/版本/平台不同，已停止且不会覆盖。'),('source provenance conflicts','已有同名镜像的源码身份不同，已停止且不会覆盖。')]
        for fragment,chinese in translations:
            if fragment in message:message=message.replace(fragment,chinese);break
        print('Local release stopped: '+message,file=sys.stderr);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
