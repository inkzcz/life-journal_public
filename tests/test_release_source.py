"""Authentication/content gates; no network, Docker, real credentials or data."""
import hashlib, json, subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import release_source as s
COMMIT = 'a' * 40
TAG = 'b' * 40

@pytest.fixture
def official(tmp_path):
    root = tmp_path / 'official'
    root.mkdir()
    content = {'VERSION': b'9.9.9\n', 'backend/app.py': b'print("fixture")\n', 'frontend/code.js': b'console.log("fixture")\n', 'docs/中文.txt': '合成内容\n'.encode(), 'run.sh': b'#!/bin/sh\ntrue\n'}
    files = {}
    for path, data in content.items():
        p = root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        files[path] = {'mode': '100755' if path == 'run.sh' else '100644', 'oid': s.blob_hash(data), 'sha256': hashlib.sha256(data).hexdigest()}
    tree = s.tree_oid(files)

    class Client:

        def __init__(self):
            self.calls = []
            self.change = None

        def get(self, path):
            self.calls.append(path)
            result = {'git/ref/tags/v9.9.9': {'object': {'type': 'tag', 'sha': TAG}}, 'git/tags/' + TAG: {'sha': TAG, 'tag': 'v9.9.9', 'object': {'type': 'commit', 'sha': COMMIT}}, 'git/commits/' + COMMIT: {'sha': COMMIT, 'tree': {'sha': tree}}, 'git/trees/' + tree + '?recursive=1': {'sha': tree, 'truncated': False, 'tree': [{'path': p, 'mode': e['mode'], 'sha': e['oid'], 'type': 'blob'} for p, e in files.items()]}}[path]
            return self.change(path, result) if self.change else result
    return (root, Client(), {'version': 'v9.9.9', 'commit': COMMIT, 'tag_object': TAG, 'tree': tree, 'files': files})

def test_annotated_release_zip_without_git_is_fully_verified(official):
    root, client, manifest = official
    proof = s.verify_source(root, client=client)
    assert proof.identity['revision'] == COMMIT
    assert proof.identity['source_verified'] is True
    assert proof.identity['revision_verified'] is False
    assert proof.identity['official_tag_object'] == TAG
    assert proof.identity['git_tree_oid'] == manifest['tree']
    assert proof.identity['source_origin'] == 'archive-channel-not-inferred'
    assert len(client.calls) == 4
    proof.recheck()

@pytest.mark.parametrize('path', ['VERSION', 'backend/app.py', 'frontend/code.js', 'docs/中文.txt', 'run.sh'])
def test_tampering_any_tracked_file_stops(official, path):
    root, client, _ = official
    (root / path).write_bytes(b'changed')
    with pytest.raises(ValueError):
        s.verify_source(root, client=client)

@pytest.mark.parametrize('operation', ['missing', 'extra', 'crlf', 'link'])
def test_missing_extra_line_endings_and_symlinks_fail(official, operation):
    root, client, _ = official
    if operation == 'missing':
        (root / 'docs/中文.txt').unlink()
    elif operation == 'extra':
        (root / 'backend/extra.py').write_text('not official')
    elif operation == 'crlf':
        (root / 'run.sh').write_bytes(b'#!/bin/sh\r\ntrue\r\n')
    else:
        (root / 'backend/app.py').unlink()
        (root / 'backend/app.py').symlink_to(root / 'run.sh')
    with pytest.raises(ValueError):
        s.verify_source(root, client=client)

def test_wrong_declared_sha_is_not_accepted_as_proof(official):
    root, client, _ = official
    with pytest.raises(ValueError, match='SHA'):
        s.verify_source(root, 'c' * 40, client=client)

@pytest.mark.parametrize('failure', ['lightweight', 'wrong-name', 'wrong-commit', 'truncated', 'bad-root', 'bad-field', 'missing-files'])
def test_abnormal_official_api_fails_closed(official, failure):
    root, client, manifest = official

    def change(path, result):
        if failure == 'lightweight' and path.startswith('git/ref'):
            return {'object': {'type': 'commit', 'sha': COMMIT}}
        if failure == 'wrong-name' and path.startswith('git/tags'):
            return result | {'tag': 'v0.0.0'}
        if failure == 'wrong-commit' and path.startswith('git/commits'):
            return result | {'sha': 'f' * 40}
        if failure == 'truncated' and path.startswith('git/trees'):
            return result | {'truncated': True}
        if failure == 'bad-root' and path.startswith('git/trees'):
            return result | {'sha': 'e' * 40}
        if failure == 'bad-field' and path.startswith('git/ref'):
            return {'object': []}
        if failure == 'missing-files' and path.startswith('git/trees'):
            return result | {'tree': []}
        return result
    client.change = change
    with pytest.raises(ValueError):
        s.verify_source(root, client=client)

def test_known_release_can_verify_offline_with_trusted_lock(official, monkeypatch, capsys):
    root, _, manifest = official
    monkeypatch.setattr(s, 'pinned', lambda version: manifest)

    class Offline:

        def get(self, path):
            raise s.Unavailable('network interrupted')
    proof = s.verify_source(root, client=Offline())
    assert proof.identity['source_verified'] and proof.identity['verification_authority'] == 'pinned-release-lock'
    assert '离线锁' in capsys.readouterr().out
    with pytest.raises(ValueError):
        s.verify_source(root, verification='online', client=Offline())

def test_unknown_version_cannot_fall_back_to_user_sha(official):
    root, _, _ = official

    class Offline:

        def get(self, path):
            raise s.Unavailable('API not reachable')
    with pytest.raises(ValueError):
        s.verify_source(root, COMMIT, client=Offline())
    with pytest.raises(ValueError):
        s.verify_source(root, COMMIT, verification='offline')

def test_api_identity_conflict_never_falls_back_to_offline(official, monkeypatch):
    root, client, manifest = official
    monkeypatch.setattr(s, 'pinned', lambda version: manifest | {'tag_object': 'd' * 40})
    with pytest.raises(ValueError, match='冲突'):
        s.verify_source(root, client=client)

def test_source_changed_after_check_is_rejected(official):
    root, client, _ = official
    proof = s.verify_source(root, client=client)
    (root / 'frontend/code.js').write_text('changed during build')
    with pytest.raises(ValueError):
        proof.recheck()

def test_only_top_level_delivery_output_is_ignored(official):
    root, client, _ = official
    (root / 'release/v9.9.9').mkdir(parents=True)
    (root / 'release/v9.9.9/fixture.tar').write_bytes(b'not a real image')
    s.verify_source(root, client=client)
    (root / 'backend/release').mkdir()
    (root / 'backend/release/extra.py').write_text('not official')
    with pytest.raises(ValueError):
        s.verify_source(root, client=client)

def test_git_checkout_clean_then_dirty_and_wrong_revision(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path / 'code').write_text('fixture')
    subprocess.run(['git', '-C', str(tmp_path), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True)
    proof = s.verify_source(tmp_path)
    assert proof.identity['revision_verified'] and proof.identity['source_verified']
    proof.recheck()
    with pytest.raises(ValueError):
        s.verify_source(tmp_path, '0' * 40)
    (tmp_path / 'code').write_text('dirty')
    with pytest.raises(ValueError):
        proof.recheck()
    with pytest.raises(ValueError):
        s.verify_source(tmp_path)

@pytest.mark.parametrize('error', ['network', 'malformed', 'array', 'oversized', 'redirect'])
def test_http_failures_never_log_or_forward_credentials(monkeypatch, capsys, error):
    import urllib.error
    monkeypatch.setenv('GH_TOKEN', 'synthetic-token-never-log')
    client = s.GitHub()

    class Response:

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def read(self, size):
            return {'malformed': b'{', 'array': b'[]', 'oversized': b'x' * (16 * 1024 * 1024 + 1)}.get(error, b'{}')

    class Opener:

        def open(self, request, timeout):
            assert request.full_url.startswith('https://api.github.com/repos/inkzcz/life-journal_public/')
            assert request.get_header('Authorization') == 'Bearer synthetic-token-never-log'
            if error == 'network':
                raise urllib.error.URLError('synthetic-token-never-log')
            if error == 'redirect':
                return s.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://invalid.example')
            return Response()
    client._opener = Opener()
    with pytest.raises(ValueError) as caught:
        client.get('git/ref/tags/v9.9.9')
    assert 'synthetic-token-never-log' not in str(caught.value)
    output = capsys.readouterr()
    assert 'synthetic-token-never-log' not in output.out + output.err
