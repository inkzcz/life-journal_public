"""Local-only linux/amd64 build/export/verification. Never pushes or deletes images.

Python 3.10+, Docker Engine/Desktop with Buildx; no Python packages required.
Uses the historical strict single-tag TAR verifier, never its publishing entrypoint.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode=True
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import release
from scripts.source_identity import identify
from scripts.release_source import verify_source
from scripts.sync_version import check as check_product_version, build_tag

ROOT = Path(__file__).resolve().parents[1]


class Docker(release.Commands):
    def build(self, *args):
        # Stream progress; do not buffer a complete build log in memory.
        # Use the context's built-in engine builder, not a selected remote builder.
        command = list(args)
        command[4:4] = ['--builder', self.context]
        ca=os.getenv('LIFE_JOURNAL_BUILD_CA')
        if not ca and os.getenv('CODEX_PROXY_CERT') and Path('/etc/ssl/certs/ca-certificates.crt').is_file():ca='/etc/ssl/certs/ca-certificates.crt'
        if ca:
            if not Path(ca).is_file():raise ValueError('Build CA file does not exist')
            command[4:4] = ['--secret','id=build_ca,src='+str(Path(ca).absolute())]
        command[4:4] = ['--progress', 'plain']
        from scripts.command_output import run_streamed
        run_streamed(command, cwd=ROOT, timeout=1800)




def local_context(commands):
    """Read local CLI metadata BEFORE contacting any daemon; reject NAS endpoints."""
    context = os.environ.get('DOCKER_CONTEXT') or commands.run('docker', 'context', 'show').strip()
    if os.environ.get('DOCKER_HOST') and not os.environ.get('DOCKER_CONTEXT'):
        endpoint = os.environ['DOCKER_HOST']
    else:
        try:
            endpoint = json.loads(commands.run('docker', 'context', 'inspect', context))[0]['Endpoints']['docker']['Host']
        except (KeyError, IndexError, TypeError):
            raise ValueError('Docker context metadata is incomplete; no daemon connection allowed') from None
    if not (endpoint.startswith('unix:///') or re.fullmatch(r'npipe:/{2,4}\./pipe/[^\s]+', endpoint)):
        raise ValueError('Only local Unix sockets/Windows named pipes are allowed; remote Docker endpoint refused')
    return context


def inspect(commands, ref):
    try:
        return json.loads(commands.run('docker', 'image', 'inspect', ref))[0]
    except subprocess.CalledProcessError as error:
        if re.search(r'(?i)(no such image|no such object)', error.stderr or ''):
            return None
        raise RuntimeError('Docker inspection failed; cannot assume tag is absent') from error


def validate_image(obj, revision, version, source=None):
    if obj is None:
        raise ValueError('Required local image is missing; run build first')
    labels = obj.get('Config', {}).get('Labels', {})
    if ((obj.get('Architecture'), obj.get('Os')) != ('amd64', 'linux')
            or labels.get('org.opencontainers.image.revision') != revision
            or labels.get('org.opencontainers.image.version') != version
            or labels.get('org.opencontainers.image.source') != 'https://github.com/inkzcz/life-journal_public'):
        raise ValueError('Local image conflicts with requested commit/version/platform; nothing overwritten')
    if source is not None:
        if labels.get('io.life-journal.build-identity') != source['build_identity'] or labels.get('io.life-journal.revision-verified') != str(source['revision_verified']).lower() or (not source['revision_verified'] and labels.get('io.life-journal.zip-tree') != source['source_tree_sha256']):
            raise ValueError('Local image source provenance conflicts; nothing overwritten')


def images(commands, revision, version, missing=False):
    result = {}
    # Preflight every component before the first build/export.
    for component in release.COMPONENTS:
        obj = inspect(commands, f'{release.image(component)}:{version}')
        if obj is not None or not missing:
            validate_image(obj, revision, version, getattr(commands,'source_identity',None))
        result[component] = obj
    return result


def build_metadata(revision,source=None):
    from datetime import datetime,timezone
    identity=source or {'revision':revision,'revision_verified':False,'revision_source':'user-provided-zip','build_identity':revision}
    return {k:identity[k] for k in ['revision','revision_verified','revision_source','build_identity']}|{'version':(ROOT/'VERSION').read_text().strip(),'built_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z')}

def build(commands, revision, version):
    from scripts import unified_images
    if unified_images.enabled(version,ROOT):return unified_images.build(commands,revision,version,ROOT)
    build_tag(version,ROOT)
    existing = images(commands, revision, version, missing=True)
    metadata=json.dumps(build_metadata(revision,getattr(commands,'source_identity',None)),separators=(',',':'))
    for component in release.COMPONENTS:
        if existing[component] is not None:
            print(f'{component}: matching local image retained', flush=True)
            continue
        context = 'frontend' if component == 'web' else 'backend'
        filename = 'Dockerfile.maintenance' if component == 'maintenance' else 'Dockerfile'
        source=getattr(commands,'source_identity',None)
        extra=[] if source is None else ['--label','io.life-journal.revision-verified='+str(source['revision_verified']).lower(),'--label','io.life-journal.build-identity='+source['build_identity']]
        if source is not None and not source['revision_verified']:extra += ['--label','io.life-journal.zip-tree='+source['source_tree_sha256']]
        commands.build('docker', 'buildx', 'build', '--load', '--provenance=false', '--sbom=false',
                       '--platform', 'linux/amd64', '--build-arg', f'APP_VERSION={source["build_identity"] if source else revision}',
                       '--build-arg', 'BUILD_INFO='+metadata,
                       '--label', f'org.opencontainers.image.revision={revision}',
                       '--label', f'org.opencontainers.image.version={version}',
                       '--label', 'org.opencontainers.image.source=https://github.com/inkzcz/life-journal_public',
                       *extra, '-f', str(ROOT/context/filename),
                       '-t', f'{release.image(component)}:{version}', str(ROOT/context))
        validate_image(inspect(commands, f'{release.image(component)}:{version}'), revision, version, source)


def export(commands, revision, version, destination):
    from scripts import unified_images
    if unified_images.enabled(version,ROOT):return unified_images.export(commands,revision,version,destination,ROOT)
    selected = images(commands, revision, version)
    destination = Path(destination).absolute()
    # Refuse partial/previous packages, even if the path is an empty directory.
    if destination.exists() or destination.is_symlink():
        raise ValueError('Output directory already exists; choose a new directory, no overwrite allowed')
    parent = destination.parent
    if not parent.is_dir():
        raise ValueError('Create the output parent directory first')
    reserve = sum(obj['Size'] for obj in selected.values()) * 1.2 + 64*1024*1024
    if shutil.disk_usage(parent).free < reserve:
        raise ValueError('Insufficient free space for three independent TARs; no export started')
    destination.mkdir()
    for component in release.COMPONENTS:
        name, checksum = release.names(component, version)
        partial = destination/(name+'.partial')
        commands.run('docker', 'save', '-o', str(partial), f'{release.image(component)}:{version}')
        partial.rename(destination/name)
        (destination/checksum).write_bytes(f'{release.digest(destination/name)}  {name}\n'.encode('ascii'))
    # Strict config identity, SHA256, single component/tag and two real loads.
    configs = release.verify_bundle(destination, revision, version, commands)
    manifest = {'format': 'life-journal-local-images-v1', 'revision': revision, 'version': version,
                'platform': 'linux/amd64', 'source':getattr(commands,'source_identity',None), 'config_digests': configs,
                'files': {release.names(c, version)[0]: release.digest(destination/release.names(c, version)[0])
                          for c in release.COMPONENTS}}
    # Completion marker is only written after all checks pass.
    with (destination/'images.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2)
    print(json.dumps(manifest, indent=2))


@contextmanager
def local_lock(version):
    # Cross-process exclusion without deleting any Docker image or user files.
    if not (release.VERSION.fullmatch(version) or release.SHA.fullmatch(version)):raise ValueError('Invalid lock version')
    path = Path(tempfile.gettempdir())/f'life-journal-local-images-{version}.lock'
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('Another local build or stale lock exists: '+str(path)+'; inspect the process before retrying, nothing removed') from None
    try:
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        os.close(fd)
        path.unlink()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['build', 'export', 'verify'])
    p.add_argument('--version', required=True)
    p.add_argument('--revision', help='Optional assertion; never a substitute for source verification')
    p.add_argument('--verification',choices=['auto','online','offline'],default='auto')
    p.add_argument('--output', type=Path, help='New bundle directory for export, existing bundle for verify')
    args = p.parse_args(argv)
    from scripts import unified_images,unified_release
    layout=unified_release if unified_images.enabled(args.version,ROOT) else release
    if args.action=='build':check_product_version(ROOT)
    proof = verify_source(ROOT,args.revision,args.verification)
    source = proof.identity
    revision = source['revision']
    release.validate_inputs(revision, args.version)
    if args.action != 'build' and args.output is None:
        p.error('export/verify requires --output')
    commands = Docker()
    commands.source_identity = source
    commands.context = local_context(commands)
    if commands.run('docker', 'info', '--format', '{{.OSType}}').strip() != 'linux':
        raise ValueError('Docker must use Linux containers')
    with local_lock(args.version):
        if args.action == 'build':
            build(commands, revision, args.version)
            proof.recheck()
            if args.output is not None:
                export(commands, revision, args.version, args.output)
                proof.recheck()
        elif args.action == 'export':
            export(commands, revision, args.version, args.output)
            proof.recheck()
        else:
            manifest = json.loads((args.output/'images.json').read_text(encoding='utf-8'))
            if manifest.get('format') != 'life-journal-local-images-v1' or manifest.get('revision') != revision or manifest.get('version') != args.version:
                raise ValueError('Package manifest does not match requested identity')
            configs = layout.verify_bundle(args.output, revision, args.version, commands)
            expected = {layout.names(c, args.version)[0]: release.digest(args.output/layout.names(c, args.version)[0]) for c in layout.COMPONENTS}
            if manifest.get('config_digests') != configs or manifest.get('files') != expected or manifest.get('platform') != 'linux/amd64':
                raise ValueError('Package manifest content differs from verified images')
            proof.recheck()
            print('SHA256, labels, config identities and repeated imports passed')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        from scripts.command_errors import describe
        print('Local image operation stopped: '+describe(error), file=sys.stderr)
        raise SystemExit(1)
