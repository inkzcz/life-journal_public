"""Local TAR verifier support; historical publisher interfaces excluded."""
import argparse
import hashlib
import json
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path
COMPONENTS = ('web', 'api', 'maintenance')
VERSION = re.compile('v[0-9]+\\.[0-9]+\\.[0-9]+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?\\Z')
SHA = re.compile('[0-9a-f]{40}\\Z')
REPOSITORY = 'inkzcz/life-journal_public'

def image(component):
    return f'ghcr.io/{REPOSITORY}-{component}'

def names(component, version):
    if component not in COMPONENTS or not (VERSION.fullmatch(version) or SHA.fullmatch(version)):
        raise ValueError('Invalid archive component/version')
    name = f'life-journal-{component}-{version}-amd64.tar'
    return (name, name + '.sha256')

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def validate_inputs(revision, version):
    if not SHA.fullmatch(revision):
        raise ValueError('Expected a full commit SHA')
    if version != revision and (not VERSION.fullmatch(version)):
        raise ValueError('Expected a fixed vMAJOR.MINOR.PATCH[-prerelease] version')

class Commands:

    def run(self, *args):
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=600).stdout

def verify_bundle(root, revision, version, commands, *, specifications=None):
    """Verify SHA, archive identity, labels, OS/arch AND real docker load/inspect."""
    validate_inputs(revision, version)
    configs = {}
    specs = specifications or {c: {'name': names(c, version)[0], 'checksum': names(c, version)[1], 'reference': f'{image(c)}:{version}'} for c in COMPONENTS}
    for component, spec in specs.items():
        name, checksum = (spec['name'], spec['checksum'])
        reference = spec['reference']
        repository = reference.rsplit(':', 1)[0]
        path = root / name
        expected = f'{digest(path)}  {name}\n'
        if (root / checksum).read_text() != expected:
            raise ValueError(f'Invalid SHA256 file: {checksum}')
        with tarfile.open(path) as archive:
            manifests = json.load(archive.extractfile('manifest.json'))
            if len(manifests) != 1:
                raise ValueError('Each TAR must contain exactly one image')
            manifest = manifests[0]
            if manifest['RepoTags'] != [reference]:
                raise ValueError('Archive contains unexpected version/component tags')
            config_bytes = archive.extractfile(manifest['Config']).read()
            config = json.loads(config_bytes)
            config_id = 'sha256:' + hashlib.sha256(config_bytes).hexdigest()
            allowed_ids = {config_id}
            if 'index.json' in archive.getnames():
                index_bytes = archive.extractfile('index.json').read()
                index = json.loads(index_bytes)
                descriptors = index.get('manifests', [])
                if not descriptors:
                    raise ValueError('Empty OCI index')
                for descriptor in descriptors:
                    ref = descriptor['digest']
                    if not re.fullmatch('sha256:[0-9a-f]{64}', ref):
                        raise ValueError('Invalid OCI manifest digest')
                    parent_bytes = archive.extractfile('blobs/sha256/' + ref.split(':')[1]).read()
                    parent = json.loads(parent_bytes)
                    if 'sha256:' + hashlib.sha256(parent_bytes).hexdigest() != ref or parent.get('config', {}).get('digest') != config_id:
                        raise ValueError('OCI index does not exclusively reference this image config')
                    allowed_ids.add(ref)
                allowed_ids.add('sha256:' + hashlib.sha256(index_bytes).hexdigest())
            labels = config.get('config', {}).get('Labels', {})
            for key, value in spec.get('required_environment', {}).items():
                matches = [entry for entry in config.get('config', {}).get('Env', []) if entry.startswith(key + '=')]
                if matches != [key + '=' + value]:
                    raise ValueError('Database runtime version differs from the required major')
            if (config.get('architecture'), config.get('os')) != ('amd64', 'linux'):
                raise ValueError('Only linux/amd64 images may be published')
            if spec.get('config_digest'):
                if config_id != spec['config_digest']:
                    raise ValueError('Archive differs from the pinned upstream database config')
            elif labels.get('org.opencontainers.image.revision') != revision or labels.get('org.opencontainers.image.version') != version:
                raise ValueError('Image labels do not match the release commit/version')
        try:
            existing = json.loads(commands.run('docker', 'image', 'inspect', reference))[0]
        except subprocess.CalledProcessError as error:
            if not re.search('(?i)(no such image|no such object)', error.stderr or ''):
                raise RuntimeError('Local image inspection failed; refusing to assume absence') from error
        else:
            if existing['Id'] not in allowed_ids or existing.get('Config', {}).get('Labels', {}) != labels:
                raise ValueError('Local version tag conflicts with archive identity/config; no import allowed')
        commands.run('docker', 'load', '-i', str(path))
        for tag in (version,):
            loaded = json.loads(commands.run('docker', 'image', 'inspect', reference))[0]
            if loaded['Id'] not in allowed_ids or loaded['Architecture'] != 'amd64' or loaded['Os'] != 'linux' or (loaded.get('Config', {}).get('Labels', {}) != labels) or (loaded.get('RootFS', {}).get('Layers', []) != config.get('rootfs', {}).get('diff_ids', [])):
                raise ValueError(f"Loaded image identity/config differs from archive: {loaded['Id']}, expected one of {sorted(allowed_ids)}")
        inventory = sorted(commands.run('docker', 'image', 'ls', '--no-trunc', '--format', '{"repository":"{{.Repository}}","tag":"{{.Tag}}","id":"{{.ID}}"}', repository).splitlines())
        commands.run('docker', 'load', '-i', str(path))
        if sorted(commands.run('docker', 'image', 'ls', '--no-trunc', '--format', '{"repository":"{{.Repository}}","tag":"{{.Tag}}","id":"{{.ID}}"}', repository).splitlines()) != inventory:
            raise ValueError('Repeated TAR load changed repository/tag/image inventory')
        configs[component] = config_id
    return configs

if __name__ == "__main__":
    raise SystemExit("Use scripts/release_local.py for the single-business-image workflow")
