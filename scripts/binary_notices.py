"""Record installed identities/notices; never certify corresponding-source closure.

Runs at image build time, reading package metadata, not executing package code.
The preserved historical catalogue is separately labelled; actual inventory is
recomputed on each build. No database or Docker access.
"""
import email.parser
import hashlib
import json
from pathlib import Path
import re
import subprocess

if __package__:
    from .license_evidence import go_build_modules, parse_control
else:
    from license_evidence import go_build_modules, parse_control

NOTICE = re.compile(r'^(?:licen[cs]e|copying|copyright|notice|authors)(?:[._-].*)?$', re.I)


def record(path):
    raw = path.read_bytes()
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('Oversized notice; manual review required')
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}


def python_packages(roots):
    result = []
    for root in roots:
        for info in sorted(root.glob('*.dist-info')):
            metadata = email.parser.Parser().parsestr((info / 'METADATA').read_text())
            notices = [record(p) for p in sorted(info.rglob('*')) if p.is_file() and NOTICE.fullmatch(p.name)]
            result.append({'name': metadata['Name'], 'version': metadata['Version'],
                           'metadata_path': str(info / 'METADATA'), 'notices': notices,
                           'license_declared': metadata['License-Expression'] or metadata['License']})
    return result


def inventory():
    status = parse_control(Path('/var/lib/dpkg/status').read_bytes())
    debian = []
    for pkg in status:
        if pkg.get('Status') != 'install ok installed':
            continue
        copyright_path = Path('/usr/share/doc') / pkg['Package'] / 'copyright'
        debian.append({'name': pkg['Package'], 'version': pkg['Version'],
                       'source_package': pkg.get('Source', pkg['Package']),
                       'notice': record(copyright_path) if copyright_path.is_file() else None})
    go_version, modules = go_build_modules(Path('/usr/bin/caddy').read_bytes())
    python = python_packages([Path('/usr/local/lib/python3.12/site-packages'),
                              Path('/opt/venv/lib/python3.12/site-packages')])
    return {'format': 'life-journal-binary-notice-inventory-v1',
            'debian': debian, 'python': python, 'caddy_go_version': go_version,
            'caddy_modules': modules,
            'caddy_version': subprocess.check_output(['caddy', 'version'], text=True).strip(),
            'browser_notices': record(Path('/srv/legal/browser-notices.json')),
            'native_database_library': 'psycopg-c built from published source; dynamically linked Debian/PGDG libpq; no psycopg-binary bundle',
            'corresponding_source_complete': False,
            'binary_redistribution_approved': False,
            'limitations': ['Installed notices and version evidence only, not a source package.',
                           'Audit exact Caddy/Go, pip vendoring, Rust and bundled native libraries.',
                           'Historical legal catalogue is a reference superset, not current closure.']}


if __name__ == '__main__':
    output = Path('/usr/share/doc/life-journal/binary-inventory.json')
    with output.open('x') as stream:
        stream.write(json.dumps(inventory(), indent=2, ensure_ascii=False) + '\n')
