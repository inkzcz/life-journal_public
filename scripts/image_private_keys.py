"""Inspect every referenced Docker-save layer without extracting files or printing keys.

Recognizes the Debian snakeoil paths and common PEM headers with key payload. This is
a targeted image regression check, not a detector for every secret/binary format.
Whiteouts and later overwrites intentionally do not hide earlier layer findings.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
import zlib


CHUNK_SIZE = 64 * 1024
PRIVATE_PEM = re.compile(
    rb'(?:'
    rb'-----BEGIN (?:(?:RSA|DSA|EC|OPENSSH|ENCRYPTED) )?PRIVATE KEY-----'
    rb'|-----BEGIN PGP PRIVATE KEY BLOCK-----'
    rb')[ \t]*\r?\n'
    rb'(?:[A-Za-z-]{1,20}:[^\r\n\x00]{0,200}\r?\n){0,4}'
    rb'(?:\r?\n)?'
    rb'(?:[A-Za-z0-9+/][ \t\r\n]{0,4}){40}'
)
SNAKEOIL_PATHS = {
    'etc/ssl/private/ssl-cert-snakeoil.key',
    'etc/ssl/certs/ssl-cert-snakeoil.pem',
}
MAX_FINDINGS = 100
MAX_PEM_BYTES = 128 * 1024
# GnuTLS 3.7.9 lib/crypto-selftests-pk.c, verified against Debian's upstream tar:
# https://deb.debian.org/debian/pool/main/g/gnutls28/gnutls28_3.7.9.orig.tar.xz
# Hash the complete PEM block plus one LF. No private bytes are stored here.
PUBLIC_GNUTLS_SELF_TESTS = frozenset({
    'c72070fc1ffb2df729650b949157c85ec03d8ec9743ba7956c03e21d385bce4e',
    '3de5d1d9ca9af8e24d29bab925c3d500c2cdd11a06c4a2c6a6b336e73bb3ad56',
    'b8369cc647a1e1e8f8e420b6b8580c36223f89b0f8e70281732d028aebf15fac',
    'd653005e4d23cf91e3572fe8148ab6db2e474924d9711838521d3ba352b193f5',
    '80ec06e06b06635bcad5c71b0e9e7a3516c02133c682a2369b09599addb8d7f3',
    'f4b1de2f94f1df2d588ff6c18290e0f7f5091267b9ef0da8433c622bad3d127a',
})


def private_pem_digests(stream):
    """Yield hashes only; incomplete/oversized plausible blocks yield None.

    The longest accepted prefix is under 2048 bytes. Overlap keeps prefixes
    crossing reads visible. Complete blocks are bounded at MAX_PEM_BYTES.
    """
    data = b''
    while True:
        chunk = stream.read(CHUNK_SIZE)
        data += chunk
        while match := PRIVATE_PEM.search(data):
            label = data[match.start()+len(b'-----BEGIN '):].split(b'-----', 1)[0]
            footer = b'-----END ' + label + b'-----'
            end = data.find(footer, match.end())
            if end < 0:
                if len(data)-match.start() > MAX_PEM_BYTES or not chunk:
                    yield None
                    data = data[match.end():]
                    continue
                data = data[match.start():]
                break
            stop = end + len(footer)
            yield (hashlib.sha256(data[match.start():stop]+b'\n').hexdigest()
                   if stop-match.start() <= MAX_PEM_BYTES else None)
            data = data[stop:]
        else:
            data = data[-2048:]
        if not chunk:
            return


def has_private_pem(stream):
    return any(True for _ in private_pem_digests(stream))


def scan_archive(path):
    report = {'passed': True, 'layers_checked': 0, 'files_checked': 0,
              'finding_count': 0, 'findings': [],
              'public_self_test_count': 0, 'public_self_tests': [],
              'scope': 'all referenced layers, including overwritten/whiteouted files; '
                       'snakeoil paths and recognized PEM headers with plausible Base64 payload only'}

    def finding(layer, name, kind):
        report['passed'] = False
        report['finding_count'] += 1
        if len(report['findings']) < MAX_FINDINGS:
            report['findings'].append({'layer': layer, 'path': name, 'kind': kind})

    with tarfile.open(path, 'r:*') as archive:
        members = {}
        for member in archive:
            if member.name in members:
                raise ValueError('Duplicate Docker archive entry')
            members[member.name] = member
        manifest = members.get('manifest.json')
        if manifest is None or not manifest.isfile() or manifest.size > 1024 * 1024:
            raise ValueError('Missing or invalid Docker manifest')
        with archive.extractfile(manifest) as stream:
            images = json.load(stream)
        if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
            raise ValueError('Expected exactly one Docker image')
        layers = images[0].get('Layers')
        if not isinstance(layers, list) or not layers or not all(isinstance(n, str) for n in layers):
            raise ValueError('Missing Docker image layers')
        for index, name in enumerate(layers, 1):
            member = members.get(name)
            if member is None or not member.isfile():
                raise ValueError('Missing or invalid referenced layer')
            with archive.extractfile(member) as stream, tarfile.open(fileobj=stream, mode='r|*') as layer:
                for entry in layer:
                    normalized = str(PurePosixPath(entry.name)).lstrip('/')
                    if normalized in SNAKEOIL_PATHS and not entry.isdir():
                        finding(index, normalized, 'default-snakeoil-path')
                    if entry.isfile():
                        report['files_checked'] += 1
                        with layer.extractfile(entry) as content:
                            for digest in private_pem_digests(content):
                                # Both provenance/content AND library location
                                # must match. Other keys in this file still fail.
                                if (digest in PUBLIC_GNUTLS_SELF_TESTS
                                        and normalized.startswith('usr/lib/')
                                        and PurePosixPath(normalized).name.startswith('libgnutls.so.')):
                                    report['public_self_test_count'] += 1
                                    if len(report['public_self_tests']) < MAX_FINDINGS:
                                        report['public_self_tests'].append({'layer': index, 'path': normalized,
                                                                          'pem_sha256': digest})
                                else:
                                    finding(index, normalized, 'private-key-pem')
                    # Streaming tar iteration otherwise retains every TarInfo.
                    layer.members.clear()
            report['layers_checked'] += 1
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = scan_archive(args.archive)
    except (OSError, ValueError, TypeError, EOFError, tarfile.TarError, zlib.error):
        # Native parser errors can contain input bytes; never echo them.
        print('Image key check failed: invalid or unreadable Docker archive.', file=sys.stderr)
        return 2
    # JSON escapes control characters in filenames; key contents are never reported.
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
