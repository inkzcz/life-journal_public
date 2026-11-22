"""Read an existing Docker-save TAR and collect actual redistribution notices.

No Docker access, builds, image imports or publication. Inspect package metadata,
never import package code. A new output directory is required. Optional network
reads are limited to integrity-checked archives recorded in the npm lockfile.
This produces evidence, not a legal approval or corresponding-source offer.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import posixpath
import subprocess
import tarfile
import threading
import zipfile
from urllib.parse import urlsplit
import urllib.request

MAX_ARCHIVE = 32 * 1024 * 1024
MAX_GO_ARCHIVE = 96 * 1024 * 1024
MAX_NOTICE = 2 * 1024 * 1024
NOTICE = re.compile(r'^(?:licen[cs]e|copying|copyright|notice|authors)(?:[._-].*)?$', re.I)
SOURCE_WRITE_LOCK = threading.Lock()


def safe_name(name):
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and all(p not in ('', '.', '..') for p in name.split('/')) and '\\' not in name and not any(ord(c) < 32 for c in name)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_notice(output, relative, data, records, origin):
    if not safe_name(relative) or len(data) > MAX_NOTICE or b'\0' in data:
        raise ValueError('Unsupported notice path/content; manual review required')
    data.decode('utf-8')
    target = output / relative
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError('Conflicting notice; nothing overwritten')
        if not any(record['path'] == relative for record in records):
            records.append({'path': relative, 'sha256': digest(data), 'origin': origin})
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    records.append({'path': relative, 'sha256': digest(data), 'origin': origin})


def parse_control(data):
    rows = []
    for block in data.decode('utf-8').split('\n\n'):
        row = {}
        for line in block.splitlines():
            if line and not line[0].isspace() and ': ' in line:
                key, value = line.split(': ', 1)
                row[key] = value
        if row:
            rows.append(row)
    return rows


def go_build_modules(binary):
    """Read the inline Go 1.18+ build-info format without executing any binary.

    Format reference: go.dev/src/debug/buildinfo/buildinfo.go. A Go compiler is
    not required; older pointer-based formats fail closed for manual review.
    """
    offset = binary.find(b'\xff Go buildinf:')
    if offset < 0 or offset + 32 > len(binary) or not binary[offset + 15] & 2:
        raise ValueError('Unsupported Go build-info format; manual review required')
    position = offset + 32
    def read_string():
        nonlocal position
        size = 0
        for shift in range(0, 70, 7):
            if position >= len(binary):
                raise ValueError('Truncated Go build-info')
            byte = binary[position]; position += 1
            size |= (byte & 127) << shift
            if not byte & 128:
                break
        else:
            raise ValueError('Invalid Go build-info length')
        if size > MAX_NOTICE or position + size > len(binary):
            raise ValueError('Invalid Go build-info size')
        data = binary[position:position + size]; position += size
        return data
    version = read_string().decode('utf-8')
    info = read_string()
    # Go module data has 16-byte start/end sentinels.
    if len(info) < 32:
        raise ValueError('Missing Go module data')
    modules = []
    for line in info[16:-16].decode('utf-8').splitlines():
        fields = line.split()
        if fields and fields[0] in ('mod', 'dep') and len(fields) >= 3:
            modules.append({'ecosystem': 'go', 'name': fields[1], 'version': fields[2],
                            'go_sum': fields[3] if len(fields) > 3 else None})
    if not modules:
        raise ValueError('No Go modules found')
    return version, modules


def image_evidence(archive_path, output, notices):
    """Apply whiteouts before selecting notices; never extract an entire layer."""
    selected = {}
    links = {}
    binary_libraries = set()
    with tarfile.open(archive_path) as archive:
        manifests = json.load(archive.extractfile('manifest.json'))
        if len(manifests) != 1:
            raise ValueError('Expected exactly one business image')
        manifest = manifests[0]
        config_data = archive.extractfile(manifest['Config']).read()
        config = json.loads(config_data)
        for layer_name in manifest['Layers']:
            with archive.extractfile(layer_name) as stream, tarfile.open(fileobj=stream, mode='r|*') as layer:
                for entry in layer:
                    name = entry.name.removeprefix('./').lstrip('/')
                    if not safe_name(name):
                        continue
                    path = PurePosixPath(name)
                    if path.name.startswith('.wh.'):
                        prefix = str(path.parent) + '/' if str(path.parent) != '.' else ''
                        removed = prefix if path.name == '.wh..wh..opq' else prefix + path.name[4:]
                        for mapping in (selected, links):
                            for candidate in list(mapping):
                                if candidate == removed or candidate.startswith(removed.rstrip('/') + '/'):
                                    mapping.pop(candidate)
                        binary_libraries = {p for p in binary_libraries if p != removed and not p.startswith(removed.rstrip('/') + '/')}
                        continue
                    if '.libs/' in name and entry.isfile():
                        binary_libraries.add(name)
                    wanted = (name == 'var/lib/dpkg/status' or name == 'usr/bin/caddy'
                              or name in {'srv/legal/browser-notices.json', 'srv/legal/THIRD_PARTY_NOTICES.txt'}
                              or name in {'usr/share/doc/life-journal/python-install-report.json',
                                          'usr/share/doc/life-journal/compiler-version.txt',
                                          'usr/share/doc/life-journal/libpq-configure.txt',
                                          'usr/share/doc/life-journal/binary-inventory.json'}
                              or '/site-packages/' in name and '.dist-info/sboms/' in name and name.endswith('.json')
                              or '/site-packages/' in name and (path.name == 'METADATA' and '.dist-info/' in name or NOTICE.fullmatch(path.name))
                              or name.startswith('usr/share/doc/') and (path.name == 'copyright' or NOTICE.fullmatch(path.name))
                              or name.startswith('usr/share/common-licenses/')
                              or name == 'usr/local/lib/python3.12/LICENSE.txt'
                              or name.endswith('/pip/_vendor/vendor.txt'))
                    if name.startswith('usr/share/doc/') and entry.issym():
                        links[name] = entry.linkname
                    if wanted and entry.isfile():
                        limit = 96 * 1024 * 1024 if name == 'usr/bin/caddy' else MAX_NOTICE
                        if entry.size > limit:
                            raise ValueError('Oversized evidence file; manual review required')
                        selected[name] = layer.extractfile(entry).read()
                    layer.members.clear()
    packages = []
    for name, data in selected.items():
        if name.endswith('.dist-info/METADATA'):
            row = parse_control(data)[0]
            packages.append({'ecosystem': 'pypi', 'name': row['Name'], 'version': row['Version'],
                             'license_declared': row.get('License-Expression') or row.get('License'),
                             'metadata_path': name})
            write_notice(output, 'image/' + name, data, notices, 'Installed package metadata')
        elif name.endswith('.json') or name.endswith('/compiler-version.txt') or name.endswith('/libpq-configure.txt'):
            write_notice(output, 'image/' + name, data, notices, 'Actual image build/source receipt or upstream SBOM')
        elif NOTICE.fullmatch(PurePosixPath(name).name) or name.startswith('usr/share/common-licenses/'):
            # Make the original package path explicit without collecting private data.
            write_notice(output, 'image/' + name, data, notices, 'Docker-save final filesystem')
        elif name.endswith('/pip/_vendor/vendor.txt'):
            write_notice(output, 'image/' + name, data, notices, 'Installed pip vendoring manifest')
            for line in data.decode('utf-8').splitlines():
                match = re.fullmatch(r'([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^\s]+)', line.split('#', 1)[0].strip())
                if match:
                    packages.append({'ecosystem': 'pypi-vendored', 'name': match[1], 'version': match[2],
                                     'vendoring_manifest': name, 'owner_package': 'pip'})
    dpkg = parse_control(selected.get('var/lib/dpkg/status', b''))
    for row in dpkg:
        if row.get('Status') == 'install ok installed':
            copyright_path = 'usr/share/doc/' + row['Package'] + '/copyright'
            resolved = copyright_path
            for _ in range(8):
                if resolved in selected:
                    break
                link = next((p for p in sorted(links, key=len, reverse=True) if resolved == p or resolved.startswith(p + '/')), None)
                if link is None:
                    break
                target = links[link]
                target = posixpath.normpath(target if target.startswith('/') else posixpath.dirname(link) + '/' + target).lstrip('/')
                if not target.startswith('usr/share/doc/'):
                    break
                resolved = target + resolved[len(link):]
            packages.append({'ecosystem': 'deb', 'name': row['Package'], 'version': row['Version'],
                             'architecture': row['Architecture'], 'source_package': row.get('Source', row['Package']),
                             'copyright_path': copyright_path,
                             'copyright_evidence_path': 'image/' + resolved if resolved in selected else None})
    caddy = selected.get('usr/bin/caddy')
    go_modules = []
    go_version = None
    if caddy:
        go_version, go_modules = go_build_modules(caddy)
    return {'image': {'architecture': config['architecture'], 'os': config['os'],
                      'config_sha256': digest(config_data),
                      'python_source': dict(value.split('=',1) for value in config.get('config',{}).get('Env',[])
                                            if value.split('=',1)[0] in {'PYTHON_VERSION','PYTHON_SHA256'}),
                      'archive_sha256': hashlib.file_digest(archive_path.open('rb'), 'sha256').hexdigest()},
            'packages': packages, 'go_version': go_version, 'go_modules': go_modules, 'bundled_native_libraries': sorted(binary_libraries)}


def retain_source(source_dir, ecosystem, data):
    """Keep verified source bytes beside evidence, never extract or execute them."""
    if source_dir is None:
        return None
    suffix = '.tgz' if ecosystem == 'npm' else '.zip'
    path = Path(source_dir) / ecosystem / (digest(data) + suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Duplicate nested npm dependencies may resolve to the same archive in
    # different workers. Serialize exclusive creation without replacing bytes.
    with SOURCE_WRITE_LOCK:
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError('Existing source evidence conflicts; nothing overwritten')
        else:
            with path.open('xb') as stream:
                stream.write(data)
    return str(path.relative_to(Path(source_dir).parent))


def npm_archive(package, source_dir=None):
    url = package.get('resolved', '')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname != 'registry.npmjs.org' or parsed.username or parsed.password:
        raise ValueError('Unsupported npm source URL')
    with urllib.request.urlopen(url, timeout=45) as response:
        if urlsplit(response.url).hostname != 'registry.npmjs.org':
            raise ValueError('Unexpected npm archive redirect')
        data = response.read(MAX_ARCHIVE + 1)
    if len(data) > MAX_ARCHIVE:
        raise ValueError('Oversized npm archive')
    integrity = package.get('integrity', '').split()
    if not any(item.startswith('sha512-') and hashlib.sha512(data).digest() == base64.b64decode(item[7:], validate=True) for item in integrity):
        raise ValueError('npm archive integrity mismatch')
    result = []
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        expanded = count = 0
        for member in archive:
            expanded += member.size; count += 1
            if expanded > 128 * 1024 * 1024 or count > 20000:
                raise ValueError('Oversized expanded npm archive')
            if member.isfile() and NOTICE.fullmatch(PurePosixPath(member.name).name):
                if member.size > MAX_NOTICE or not safe_name(member.name):
                    raise ValueError('Unsupported npm notice')
                result.append((member.name, archive.extractfile(member).read()))
    retained = retain_source(source_dir, 'npm', data)
    if retained:
        package['retained_source_archive'] = retained
        package['retained_source_sha256'] = digest(data)
    return result


def go_archive(module, source_dir=None):
    """Verify module source against the binary's Go h1 directory checksum."""
    name, version = module['name'], module['version']
    if version == '(devel)':
        return []
    escape = lambda value: ''.join('!' + c.lower() if c.isupper() else c for c in value)
    if not re.fullmatch(r'[A-Za-z0-9._~!/+\-]+', name) or not re.fullmatch(r'v[0-9A-Za-z.+\-]+', version):
        raise ValueError('Unsupported Go module identity')
    url = 'https://proxy.golang.org/' + escape(name) + '/@v/' + escape(version) + '.zip'
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(MAX_GO_ARCHIVE + 1)
    if len(data) > MAX_GO_ARCHIVE:
        raise ValueError('Oversized Go module archive')
    found = []
    sums = hashlib.sha256()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = sorted((m for m in archive.infolist() if not m.is_dir()), key=lambda m: m.filename)
        if sum(m.file_size for m in members) > 512 * 1024 * 1024:
            raise ValueError('Oversized expanded Go source')
        for member in members:
            if not safe_name(member.filename):
                raise ValueError('Invalid Go source path')
            content = archive.read(member)
            sums.update((digest(content) + '  ' + member.filename + '\n').encode())
            if NOTICE.fullmatch(PurePosixPath(member.filename).name):
                if len(content) > MAX_NOTICE:
                    raise ValueError('Oversized Go notice')
                found.append((member.filename.split('/', 1)[-1], content))
    computed = 'h1:' + base64.b64encode(sums.digest()).decode()
    if computed != module.get('go_sum'):
        raise ValueError('Go source h1 checksum mismatch')
    retained = retain_source(source_dir, 'go', data)
    if retained:
        module['retained_source_archive'] = retained
        module['retained_source_sha256'] = digest(data)
    return found


def go_evidence(modules, output, notices, source_dir=None):
    with ThreadPoolExecutor(max_workers=6) as pool:
        for module, files in zip(modules, pool.map(lambda module: go_archive(module, source_dir), modules)):
            paths = []
            for name, data in files:
                # Keep module version and original subdirectories distinct.
                relative = 'go/' + module['name'] + '@' + module['version'] + '/' + name
                write_notice(output, relative, data, notices, 'Go module archive verified against binary h1')
                paths.append(relative)
            module['notice_files'] = paths
            module['status'] = 'verified-module-notices' if paths else 'source-review-required'


def frontend_evidence(lock_path, output, notices, fetch, source_dir=None):
    packages = json.loads(lock_path.read_text())['packages']
    entries = [(path, package) for path, package in sorted(packages.items()) if path]
    def collect(item):
        path, package = item
        if not safe_name(path):
            raise ValueError('Invalid npm package path')
        found = npm_archive(package, source_dir) if fetch else []
        return path, package, found
    result = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for path, package, found in pool.map(collect, entries):
            package_files = []
            for name, data in found:
                relative = 'npm/' + path.removeprefix('node_modules/') + '/' + name
                write_notice(output, relative, data, notices, package.get('resolved', 'lockfile'))
                package_files.append(relative)
            result.append({'ecosystem': 'npm', 'package_path': path, 'version': package['version'],
                           'license_declared': package.get('license'), 'development_only': package.get('dev', False),
                           'optional': package.get('optional', False), 'notice_files': package_files,
                           'status': 'archive-notices-collected' if found else 'notice-review-required',
                           'archive_integrity': package.get('integrity'), 'source': package.get('resolved'),
                           'retained_source_archive':package.get('retained_source_archive'),
                           'retained_source_sha256':package.get('retained_source_sha256')})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-archive', required=True, type=Path)
    parser.add_argument('--frontend-lock', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--fetch-npm-archives', action='store_true')
    parser.add_argument('--fetch-go-archives', action='store_true')
    parser.add_argument('--retain-source-archives', action='store_true',
                        help='Retain integrity-verified npm/Go source archives; does not complete all source obligations')
    args = parser.parse_args()
    output = args.output_dir
    if output.exists() or output.is_symlink() or any(p.is_symlink() for p in output.absolute().parents):
        parser.error('New output directory without symlink parents required; nothing overwritten')
    output.mkdir(parents=True, mode=0o700)
    notices = []
    phase = 'image-evidence'
    try:
        report = image_evidence(args.image_archive, output, notices)
        phase = 'npm-archive-evidence'
        source_dir = output / 'sources' if args.retain_source_archives else None
        report['packages'] += frontend_evidence(args.frontend_lock, output, notices, args.fetch_npm_archives, source_dir)
        if args.fetch_go_archives:
            phase = 'go-module-evidence'
            go_evidence(report['go_modules'], output, notices, source_dir)
        report.update(format='life-journal-license-evidence-v1', notices=notices,
                      publication_approved=False, corresponding_source_complete=False,
                      limitations='Evidence only. Missing notices, Go sources, bundled native libraries, license choices and each actual release require review.')
        (output / 'inventory.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.SubprocessError) as error:
        print(json.dumps({'failed_phase': phase, 'error_type': type(error).__name__,
                          'detail': str(error) if type(error) is ValueError else 'Native input/transport error; raw data withheld',
                          'exit_code': 1, 'http_status': getattr(error, 'code', None),
                          'partial_output_retained': True}))
        return 1
    print(json.dumps({'packages': len(report['packages']), 'go_modules': len(report['go_modules']),
                      'notices': len(notices), 'bundled_libraries': len(report['bundled_native_libraries']),
                      'publication_approved': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
