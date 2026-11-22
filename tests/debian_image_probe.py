"""Execute inside the built business image; never resolve a database image."""
import argparse
import json
from pathlib import Path
import subprocess

DEFAULT_KEY_PROBE = r'''
import os
paths = ('/etc/ssl/private/ssl-cert-snakeoil.key', '/etc/ssl/certs/ssl-cert-snakeoil.pem')
assert all(not os.path.lexists(path) for path in paths), 'Unexpected default snakeoil key/certificate'
'''

PROBE = r'''
import json, os, platform, shutil, subprocess, sys
from pathlib import Path
release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
assert release['ID'].strip('"') == 'debian'
assert release['VERSION_CODENAME'].strip('"') == 'bookworm'
assert sys.version_info[:2] == (3, 12)
assert os.getuid() == os.getgid() == 10001
assert platform.machine() == 'x86_64'
# Check actual in-image legal copies, not just source-tree presence.
import hashlib
legal=Path('/usr/share/doc/life-journal')
assert hashlib.sha256((legal/'LICENSE').read_bytes()).hexdigest() == '3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986'
assert 'Copyright (C) 2026 inkzcz' in (legal/'COPYRIGHT.md').read_text()
notices=json.loads((legal/'notice-index.json').read_text())['files']
assert len(notices)==410
for notice in notices:
    relative=Path(notice['path']).relative_to('third_party')
    assert hashlib.sha256((legal/relative).read_bytes()).hexdigest()==notice['sha256']
    assert (legal/relative).read_bytes()==(Path('/srv/legal')/relative).read_bytes()
browser=json.loads(Path('/srv/legal/browser-notices.json').read_text())
assert browser['packages'] and browser['third_party_relicensed'] is False
for package in browser['packages']:
    for notice in package['notices']:
        assert hashlib.sha256(notice['text'].encode()).hexdigest()==notice['sha256']
inventory=json.loads((legal/'binary-inventory.json').read_text())
assert inventory['debian'] and inventory['python'] and inventory['caddy_modules']
assert inventory['corresponding_source_complete'] is False
assert inventory['binary_redistribution_approved'] is False
for package in inventory['debian']:
    if package['notice']:
        assert hashlib.sha256(Path(package['notice']['path']).read_bytes()).hexdigest()==package['notice']['sha256']
def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()
tools = {}
for name in ('initdb', 'pg_ctl', 'postgres', 'pg_dump', 'pg_restore'):
    path = shutil.which(name)
    assert path, name
    version = run(path, '--version')
    assert ' 17.' in version, version
    tools[name] = {'path': path, 'version': version}
assert not run('pg_lsclusters', '-h'), 'Unexpected baked database cluster'
assert not shutil.which('node') and not shutil.which('npm')
caddy = run('caddy', 'version')
linked = subprocess.run(['ldd', '/usr/bin/caddy'], text=True, capture_output=True)
linkage = linked.stdout + linked.stderr
assert 'not found' not in linkage
assert linked.returncode == 0 or 'not a dynamic executable' in linkage or 'statically linked' in linkage, linkage
# GNU wget accepts the legacy -Y switch without listing it in --help.
# Exercise the exact existing Compose health command against loopback only.
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class Healthy(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
    def log_message(self, *args):
        pass
with ThreadingHTTPServer(('127.0.0.1', 0), Healthy) as server:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        subprocess.run(['wget', '-q', '-Y', 'off', '--spider',
                        'http://127.0.0.1:'+str(server.server_port)+'/'],
                       check=True, capture_output=True, timeout=10)
    finally:
        server.shutdown()
        thread.join(timeout=5)
packages = run('dpkg-query', '-W', '-f=${Package}=${Version}\n', 'libc6', 'libpq5', 'postgresql-17', 'postgresql-client-17', 'ca-certificates')
print(json.dumps({'python': sys.version, 'executable': sys.executable, 'libc': platform.libc_ver(), 'os': release, 'tools': tools, 'caddy': caddy, 'caddy_linkage': linkage.strip(), 'wget_compose_healthcheck': 'passed', 'packages': packages, 'uid': os.getuid(), 'gid': os.getgid(), 'preserved_legal_texts':len(notices), 'browser_packages':len(browser['packages']), 'binary_source_closure':'pending'}, ensure_ascii=False))
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-tag', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # /etc/ssl/private is not traversable by the app user. Check as root rather
    # than mistaking an access failure for absence; never read/print key bytes.
    subprocess.run([
        'docker', 'run', '--rm', '--pull=never', '--platform', 'linux/amd64',
        '--user', '0:0', '--read-only', '--network', 'none',
        '--entrypoint', 'python', 'life-journal:' + args.image_tag, '-c', DEFAULT_KEY_PROBE,
    ], check=True, capture_output=True, text=True)
    output = subprocess.check_output([
        'docker', 'run', '--rm', '--pull=never', '--platform', 'linux/amd64',
        '--user', '10001:10001', '--read-only', '--tmpfs', '/tmp:rw,nosuid,size=64m',
        '--entrypoint', 'python', '-i', 'life-journal:' + args.image_tag, '-c', PROBE,
    ], text=True)
    report = json.loads(output)
    report['default_snakeoil_key_and_certificate_absent'] = True
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
