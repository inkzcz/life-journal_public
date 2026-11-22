"""Collect exact upstream source archives for one already verified business TAR.

No Docker, package installation, source execution, database or publishing access.
Sources are kept as archives, never extracted. A new private output is required.
TLS authenticates publisher metadata; published archive checksums are mandatory.
Debian snapshot SHA1 locators are supplemented by .dsc SHA256 checksums (the
snapshot locator is not described as an APT or uploader signature verification).
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import time
import tomllib
from urllib.parse import quote, urlsplit
import urllib.error
import urllib.request

MAX_FILE = 512 * 1024 * 1024
MAX_METADATA = 32 * 1024 * 1024
HOSTS = frozenset({'snapshot.debian.org', 'apt.postgresql.org', 'apt-archive.postgresql.org',
    'pypi.org', 'files.pythonhosted.org', 'static.crates.io', 'go.dev', 'dl.google.com',
    'raw.githubusercontent.com', 'codeload.github.com', 'api.github.com', 'www.python.org',
    'registry.npmjs.org', 'code.haverbeke.berlin'})


def checked_url(url):
    value = urlsplit(url)
    if (value.scheme != 'https' or value.hostname not in HOSTS or value.username
            or value.password or value.fragment):
        raise ValueError('Unapproved source publisher URL')
    return url


def fetch(url, limit=MAX_METADATA):
    checked_url(url)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={
                    'User-Agent': 'Life-Journal-corresponding-source/1'}), timeout=90) as response:
                checked_url(response.url)
                raw = response.read(limit + 1)
            if len(raw) > limit:
                raise ValueError('Source metadata exceeds size limit')
            return raw
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            time.sleep(min(2 ** attempt, 8))
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(min(2 ** attempt, 8))


def json_fetch(url):
    if urlsplit(checked_url(url)).hostname == 'api.github.com' and shutil.which('gh'):
        result = subprocess.run(['gh','api','--method','GET',url],
                                capture_output=True,text=True,timeout=90)
        if result.returncode or len(result.stdout)>MAX_METADATA:
            raise ValueError('Public upstream GitHub source lookup failed')
        return json.loads(result.stdout)
    return json.loads(fetch(url))


def file_name(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+%~:\-]*', value) or '..' in value:
        raise ValueError('Invalid upstream source filename')
    return value


def save_download(url, path, *, sha256=None, sha1=None, size=None):
    if not (sha256 or sha1):
        raise ValueError('Published source checksum required')
    checked_url(url)
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ValueError('Source destination exists; nothing overwritten')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Complete each download before making its final evidence filename visible.
    part = path.with_name(path.name + '.partial')
    digests = {'sha256': hashlib.sha256(), 'sha1': hashlib.sha1()}
    total = 0
    with urllib.request.urlopen(url, timeout=120) as response, part.open('xb') as stream:
        checked_url(response.url)
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_FILE:
                raise ValueError('Source archive exceeds size limit')
            for digest in digests.values():
                digest.update(chunk)
            stream.write(chunk)
    if ((sha256 and digests['sha256'].hexdigest() != sha256)
            or (sha1 and digests['sha1'].hexdigest() != sha1)
            or (size is not None and size != total)):
        raise ValueError('Published source size/checksum mismatch')
    part.rename(path)
    return {'path': str(path), 'sha256': digests['sha256'].hexdigest(),
            'size': total, 'url': url}


def control(text):
    """Parse Debian control continuations, including a clearsigned .dsc body."""
    if text.startswith('-----BEGIN PGP SIGNED MESSAGE-----'):
        text = text.split('\n\n', 1)[1].split('-----BEGIN PGP SIGNATURE-----', 1)[0]
        text = '\n'.join(line[2:] if line.startswith('- ') else line for line in text.splitlines())
    result = {}
    previous = None
    for line in text.splitlines():
        if not line:
            continue
        if line[0].isspace():
            if previous:
                result[previous] += '\n' + line.strip()
        else:
            key, separator, value = line.partition(':')
            if not separator or key in result:
                raise ValueError('Invalid source descriptor')
            result[key] = value.strip()
            previous = key
    return result


def dsc_files(raw, name, version):
    fields = control(raw.decode('utf-8'))
    if fields.get('Source') != name or fields.get('Version') != version:
        raise ValueError('Source descriptor package/version mismatch')
    rows = []
    for line in fields.get('Checksums-Sha256', '').strip().splitlines():
        digest, size, filename = line.split()
        if not re.fullmatch('[0-9a-f]{64}', digest) or not size.isdigit():
            raise ValueError('Invalid source checksum descriptor')
        rows.append({'name': file_name(filename), 'sha256': digest, 'size': int(size)})
    if not rows or len({row['name'] for row in rows}) != len(rows):
        raise ValueError('Missing/duplicate source archive checksums')
    return rows


def source_identity(package):
    source = package.get('source_package') or package['name']
    match = re.fullmatch(r'([a-z0-9][a-z0-9+.-]*)(?: \(([^()/\s]+)\))?', source)
    if not match:
        raise ValueError('Invalid installed source package identity')
    return match[1], match[2] or package['version']


def debian_source(name, version, output):
    directory = output / 'sources/debian' / name / quote(version, safe='')
    api = f'https://snapshot.debian.org/mr/package/{quote(name)}/{quote(version, safe="")}/srcfiles'
    index = json_fetch(api)
    if index.get('package') != name or index.get('version') != version:
        raise ValueError('Snapshot source identity mismatch')
    files = {}
    for entry in index['result']:
        locator = entry['hash']
        if not re.fullmatch('[0-9a-f]{40}', locator):
            raise ValueError('Invalid snapshot locator')
        info = json_fetch('https://snapshot.debian.org/mr/file/' + locator + '/info')
        for location in info['result']:
            filename = file_name(location['name'])
            files[filename] = locator
    descriptors = [p for p in files if p.endswith('.dsc')]
    if len(descriptors) != 1:
        raise ValueError('Expected one exact Debian source descriptor')
    dsc = descriptors[0]
    record = save_download('https://snapshot.debian.org/file/' + files[dsc],
                           directory / dsc, sha1=files[dsc])
    records = [record]
    for row in dsc_files((directory / dsc).read_bytes(), name, version):
        if row['name'] not in files:
            raise ValueError('Snapshot does not provide a required source archive')
        records.append(save_download('https://snapshot.debian.org/file/' + files[row['name']],
            directory / row['name'], sha256=row['sha256'], sha1=files[row['name']], size=row['size']))
    return {'ecosystem': 'deb', 'name': name, 'version': version, 'files': records,
            'verification': 'TLS-authenticated Debian snapshot descriptor and published .dsc SHA256; not an APT signature assertion'}


def pgdg_source(name, version, output):
    # These are installed PostgreSQL TOOL/LIBRARY source packages, never a
    # database image query, build, pull, tag or export.
    directory = output / 'sources/debian' / name / quote(version, safe='')
    prefix = name[:4] if name.startswith('lib') else name[0]
    base = f'https://apt.postgresql.org/pub/repos/apt/pool/main/{prefix}/{name}/'
    filename = file_name(name + '_' + version.split(':')[-1] + '.dsc')
    raw = fetch(base + quote(filename))
    rows = dsc_files(raw, name, version)
    directory.mkdir(parents=True)
    (directory / filename).write_bytes(raw)
    records = [{'path': str(directory / filename), 'sha256': hashlib.sha256(raw).hexdigest(),
                'size': len(raw), 'url': base + quote(filename)}]
    for row in rows:
        records.append(save_download(base + quote(row['name']), directory / row['name'],
                                     sha256=row['sha256'], size=row['size']))
    return {'ecosystem': 'deb', 'name': name, 'version': version, 'files': records,
            'verification': 'TLS-authenticated PGDG exact .dsc and its published source archive SHA256'}


def pypi_source(name, version, output):
    if not re.fullmatch(r'[A-Za-z0-9._-]+', name) or not re.fullmatch(r'[0-9A-Za-z.!+_-]+', version):
        raise ValueError('Invalid Python source identity')
    data = json_fetch(f'https://pypi.org/pypi/{quote(name)}/{quote(version)}/json')
    archives = [item for item in data['urls'] if item['packagetype'] == 'sdist']
    if len(archives) != 1:
        raise ValueError('Exact Python sdist missing or ambiguous: ' + name + '@' + version)
    item = archives[0]
    target = output / 'sources/python' / name / file_name(item['filename'])
    record = save_download(item['url'], target, sha256=item['digests']['sha256'], size=item['size'])
    return {'ecosystem': 'pypi', 'name': name, 'version': version, 'files': [record],
            'published_artifacts': {p['filename']: p['digests']['sha256'] for p in data['urls']}}


def archive_members(path):
    """Read bounded source files, without extracting or importing anything."""
    with tarfile.open(path, mode='r:*') as archive:
        total = count = 0
        for member in archive:
            count += 1
            total += member.size
            if count > 200000 or total > 2 * 1024 ** 3:
                raise ValueError('Oversized expanded source archive')
            if not member.isfile():
                continue
            if (member.name.startswith('/') or '..' in PurePosixPath(member.name).parts
                    or '\\' in member.name):
                raise ValueError('Unsafe upstream archive path')
            yield member.name, member, archive


def cargo_sources(records, output):
    collected = []
    seen = set()
    for package in records:
        if package['ecosystem'] != 'pypi':
            continue
        for record in package['files']:
            for name, member, archive in archive_members(record['path']):
                if not name.endswith('/Cargo.lock') or member.size > MAX_METADATA:
                    continue
                lock = tomllib.loads(archive.extractfile(member).read().decode())
                for crate in lock.get('package', []):
                    if not crate.get('source', '').startswith('registry+'):
                        continue
                    key = crate['name'], crate['version']
                    if key in seen:
                        continue
                    seen.add(key)
                    if not re.fullmatch(r'[A-Za-z0-9_-]+', key[0]) or not re.fullmatch(r'[0-9A-Za-z.+_-]+', key[1]):
                        raise ValueError('Invalid Cargo source identity')
                    filename = file_name(key[0] + '-' + key[1] + '.crate')
                    url = 'https://static.crates.io/crates/' + key[0] + '/' + filename
                    collected.append({'ecosystem': 'cargo', 'name': key[0], 'version': key[1],
                        'files': [save_download(url, output/'sources/cargo'/filename, sha256=crate['checksum'])]})
    return collected


def python_runtime_source(image, output):
    env = image.get('python_source', {})
    version, digest = env.get('PYTHON_VERSION'), env.get('PYTHON_SHA256')
    if not version or not re.fullmatch(r'3\.12\.\d+', version) or not re.fullmatch('[0-9a-f]{64}', digest or ''):
        raise ValueError('Pinned CPython source identity missing from image')
    HOSTS_URL = 'https://www.python.org/ftp/python/' + version + '/Python-' + version + '.tar.xz'
    # python.org is the official publisher; the image pins the exact SHA256.
    return save_download(HOSTS_URL, output/'sources/cpython'/('Python-'+version+'.tar.xz'), sha256=digest)


def published_github_source(repository, revision, output):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Invalid public upstream source commit')
    filename = file_name(repository.replace('/', '-') + '-' + revision + '.tar.gz')
    target = output/'sources/upstream-git'/filename
    if target.exists():
        return {'path': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                'size': target.stat().st_size, 'repository': repository, 'revision': revision}
    url = 'https://codeload.github.com/' + repository + '/tar.gz/' + revision
    # A public publisher's immutable Git commit is the source identity; preserve
    # the retrieved archive SHA256 as an additional transport/content receipt.
    raw = fetch(url, limit=MAX_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(raw)
    return {'path': str(target), 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw),
            'url': url, 'repository': repository, 'revision': revision}


def github_tag_source(repository, tag, output):
    reference = json_fetch('https://api.github.com/repos/'+repository+'/git/ref/tags/'+quote(tag,safe=''))['object']
    if reference['type']=='tag':
        reference=json_fetch('https://api.github.com/repos/'+repository+'/git/tags/'+reference['sha'])['object']
    if reference['type']!='commit':
        raise ValueError('Upstream release tag does not resolve to a source commit')
    return published_github_source(repository,reference['sha'],output)


def browser_sources(browser, output):
    records = []
    resolved_releases = {}
    for package in browser['packages']:
        name, version = package['name'], package['version']
        metadata = json_fetch('https://registry.npmjs.org/' + quote(name, safe='') + '/' + quote(version))
        repo = metadata.get('repository', {})
        repo = repo.get('url', '') if isinstance(repo, dict) else repo
        match = re.fullmatch(r'(?:git\+)?(?:https://|git://)github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?', repo)
        forgejo = re.fullmatch(r'(?:git\+)?https://code\.haverbeke\.berlin/(prosemirror/[A-Za-z0-9_.-]+?)(?:\.git)?',repo)
        if not match and not forgejo:
            raise ValueError('Browser preferred source repository unresolved: ' + name + '@' + version)
        revision = metadata.get('gitHead')
        if forgejo:
            if not re.fullmatch('[0-9a-f]{40}',revision or ''):
                raise ValueError('Exact upstream ProseMirror source commit missing: '+name)
            filename=file_name(name.replace('/','-').replace('@','')+'-'+revision+'.tar.gz')
            target=output/'sources/upstream-git'/filename
            url='https://code.haverbeke.berlin/'+forgejo[1]+'/archive/'+revision+'.tar.gz'
            raw=fetch(url,limit=MAX_FILE);target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(raw)
            records.append({'ecosystem':'browser-preferred-source','name':name,'version':version,
                'files':[{'path':str(target),'url':url,'revision':revision,'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)}]})
            continue
        revision=revision or resolved_releases.get((match[1],version))
        if not revision:
            # Explicit release-tag lookup only, never a moving branch/default.
            for tag in ('v'+version, version):
                try:
                    ref = json_fetch('https://api.github.com/repos/' + match[1] + '/git/ref/tags/' + quote(tag, safe=''))['object']
                    if ref['type'] == 'tag':
                        ref = json_fetch('https://api.github.com/repos/' + match[1] + '/git/tags/' + ref['sha'])['object']
                    if ref['type'] == 'commit':
                        revision = ref['sha'];break
                except urllib.error.HTTPError as error:
                    if error.code != 404:
                        raise
        if not revision:
            raise ValueError('Browser immutable preferred source commit missing: ' + name + '@' + version)
        resolved_releases[match[1],version]=revision
        records.append({'ecosystem': 'browser-preferred-source', 'name': name, 'version': version,
                        'files': [published_github_source(match[1], revision, output)]})
    return records


def go_runtime_source(version, output):
    if not re.fullmatch(r'go1\.[0-9]+\.[0-9]+', version):
        raise ValueError('Unsupported actual Go toolchain identity')
    releases = json_fetch('https://go.dev/dl/?mode=json&include=all')
    files = [f for release in releases if release['version'] == version for f in release['files'] if f['kind'] == 'source']
    if len(files) != 1:
        raise ValueError('Exact Go toolchain source/checksum unavailable')
    item = files[0]
    return save_download('https://go.dev/dl/' + file_name(item['filename']),
        output/'sources/go-runtime'/item['filename'], sha256=item['sha256'], size=item['size'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browser-notices', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('New private output directory required; nothing overwritten')
    args.output.mkdir(parents=True, mode=0o700)
    inventory = json.loads(args.inventory.read_text())
    records = []
    phase = 'debian-corresponding-source'
    try:
        identities = sorted({source_identity(p) for p in inventory['packages'] if p['ecosystem'] == 'deb'})
        def collect(identity):
            name, version = identity
            try:
                result = (pgdg_source if '.pgdg' in version else debian_source)(name, version, args.output)
            except Exception as error:
                raise ValueError('Exact source unavailable/invalid: ' + name + '=' + version
                                 + ' (' + type(error).__name__ + ')') from None
            print(json.dumps({'source_complete': name, 'version': version}), flush=True)
            return result
        with ThreadPoolExecutor(max_workers=4) as pool:
            records.extend(pool.map(collect, identities))
        phase = 'python-corresponding-source'
        python = sorted({(p['name'], p['version']) for p in inventory['packages'] if p['ecosystem'] == 'pypi'})
        for name, version in python:
            records.append(pypi_source(name, version, args.output))
            print(json.dumps({'source_complete': name, 'version': version}), flush=True)
        phase = 'cargo-source-checksums'
        records.extend(cargo_sources(records, args.output))
        phase = 'cpython-source-checksum'
        runtime = python_runtime_source(inventory['image'], args.output)
        records.append({'ecosystem': 'cpython', 'files': [runtime]})
        phase = 'browser-preferred-source'
        records.extend(browser_sources(json.loads(args.browser_notices.read_text()), args.output))
        phase = 'go-runtime-source'
        records.append({'ecosystem':'go-runtime', 'files':[go_runtime_source(inventory['go_version'],args.output)]})
        phase = 'pillow-upstream-build-recipe'
        pillow=next(r for r in records if r.get('ecosystem')=='pypi' and r['name'].lower()=='pillow')
        upstream=github_tag_source('python-pillow/Pillow',pillow['version'],args.output)
        records.append({'ecosystem':'upstream-build-recipe','name':'Pillow','version':pillow['version'],'files':[upstream]})
        phase = 'fribidi-upstream-notice-and-ancestry'
        records.append({'ecosystem':'upstream-ancestry','name':'FriBiDi','version':'1.0.16',
                        'files':[github_tag_source('fribidi/fribidi','v1.0.16',args.output)]})
        for package in records:
            for record in package['files']:
                record['path'] = str(Path(record['path']).relative_to(args.output))
        report = {'format': 'life-journal-exact-sources-v1', 'records': records,
                  'source_archive_count': sum(len(p['files']) for p in records),
                  'binary_distribution_complete': False,
                  'remaining_gate': 'Bind all source/notices/build/replacement receipts to the same verified business image and application source.'}
        (args.output/'sources.json').write_text(json.dumps(report, indent=2)+'\n')
    except Exception as error:
        print(json.dumps({'failed_phase': phase, 'type': type(error).__name__,
            'detail': str(error) if isinstance(error, ValueError) else 'Publisher transport or archive error; raw data withheld',
            'partial_evidence_retained': True}), flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
