"""Synthetic layer data only; no real credentials or downloaded keys."""
import io
import hashlib
import json
from pathlib import Path
import tarfile

import pytest

from scripts import image_private_keys as keys


def pem_header(label):
    # Construct synthetic test markers at runtime; no literal credential block.
    return b'-----BEGIN ' + label.encode() + b'-----'


def tar_bytes(entries, mode='w'):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode=mode) as archive:
        for name, data in entries:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return result.getvalue()


def image(tmp_path, *layers):
    names = [f'layer-{i}/layer.tar' for i in range(len(layers))]
    entries = [('manifest.json', json.dumps([{'Layers': names}]).encode())]
    entries += [(name, data) for name, data in zip(names, layers)]
    path = tmp_path/'image.tar'
    path.write_bytes(tar_bytes(entries))
    return path


@pytest.mark.parametrize('later', [
    [('etc/ssl/private/.wh.ssl-cert-snakeoil.key', b'')],
    [('etc/ssl/private/ssl-cert-snakeoil.key', b'overwritten synthetic content')],
    [('etc/ssl/private/.wh..wh..opq', b'')],
])
def test_later_deletion_or_overwrite_never_hides_a_key(tmp_path, later):
    path = image(tmp_path, tar_bytes([('./etc/ssl/private/ssl-cert-snakeoil.key', b'synthetic')]),
                 tar_bytes(later))
    report = keys.scan_archive(path)
    assert not report['passed'] and report['layers_checked'] == 2
    assert report['findings'][0]['layer'] == 1


@pytest.mark.parametrize('label', ['PRIVATE KEY', 'RSA PRIVATE KEY', 'EC PRIVATE KEY',
                                  'DSA PRIVATE KEY', 'OPENSSH PRIVATE KEY',
                                  'ENCRYPTED PRIVATE KEY', 'PGP PRIVATE KEY BLOCK'])
def test_recognized_headers_at_arbitrary_paths_and_across_chunks(tmp_path, label):
    header = pem_header(label)
    content = b'x'*(keys.CHUNK_SIZE-7) + header + b'\n' + b'Q'*64 + b'\n'
    report = keys.scan_archive(image(tmp_path, tar_bytes([('unexpected/location', content)])))
    assert report['finding_count'] == 1
    assert report['findings'][0]['kind'] == 'private-key-pem'


def test_library_format_strings_are_not_private_key_material(tmp_path):
    content = b'\x7fELF\x00'+pem_header('RSA PRIVATE KEY')+b'\n\x00-----END RSA PRIVATE KEY-----\x00'
    report = keys.scan_archive(image(tmp_path, tar_bytes([('usr/lib/synthetic.so', content)])))
    assert report['passed']


def test_crlf_encrypted_pem_preamble_and_payload_crossing_read_boundary(tmp_path):
    prefix = pem_header('RSA PRIVATE KEY')+b'\r\nProc-Type: 4,ENCRYPTED\r\nDEK-Info: AES-256-CBC,SYNTHETIC\r\n\r\n'
    content = b'x'*(keys.CHUNK_SIZE-len(prefix)-8) + prefix + b'Q'*64 + b'\r\n'
    report = keys.scan_archive(image(tmp_path, tar_bytes([('unexpected/encrypted.pem', content)])))
    assert not report['passed']


def synthetic_pem(value=b'Q'):
    return pem_header('PRIVATE KEY')+b'\n'+value*64+b'\n-----END PRIVATE KEY-----\n'


def test_public_self_test_requires_exact_digest_and_library_location(tmp_path, monkeypatch):
    fixture = synthetic_pem()
    monkeypatch.setattr(keys, 'PUBLIC_GNUTLS_SELF_TESTS', {hashlib.sha256(fixture).hexdigest()})
    library = 'usr/lib/x86_64-linux-gnu/libgnutls.so.synthetic'
    report = keys.scan_archive(image(tmp_path, tar_bytes([(library, fixture)])))
    assert report['passed'] and report['public_self_test_count'] == 1
    report = keys.scan_archive(image(tmp_path, tar_bytes([('app/unnecessary.key', fixture)])))
    assert not report['passed'] and report['public_self_test_count'] == 0


def test_known_self_test_does_not_hide_an_unknown_key_in_the_same_library(tmp_path, monkeypatch):
    fixture = synthetic_pem()
    monkeypatch.setattr(keys, 'PUBLIC_GNUTLS_SELF_TESTS', {hashlib.sha256(fixture).hexdigest()})
    library = 'usr/lib/x86_64-linux-gnu/libgnutls.so.synthetic'
    report = keys.scan_archive(image(tmp_path, tar_bytes([(library, fixture+b'\x00'+synthetic_pem(b'R'))])))
    assert not report['passed'] and report['public_self_test_count'] == report['finding_count'] == 1


def test_oversized_or_incomplete_key_is_never_treated_as_public_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(keys, 'PUBLIC_GNUTLS_SELF_TESTS', set())
    value = pem_header('PRIVATE KEY')+b'\n'+b'Q'*(keys.MAX_PEM_BYTES+1)
    for suffix in (b'', b'\n-----END PRIVATE KEY-----\n'):
        report = keys.scan_archive(image(tmp_path, tar_bytes([('app/large.key', value+suffix)])))
        assert not report['passed'] and report['finding_count'] == 1


def test_public_certificates_and_signing_keys_are_not_private_keys(tmp_path):
    content = b'-----BEGIN CERTIFICATE-----\nSYNTHETIC\n-----BEGIN PGP PUBLIC KEY BLOCK-----'
    report = keys.scan_archive(image(tmp_path, tar_bytes([('usr/share/keyrings/public.pem', content)])))
    assert report['passed'] and report['layers_checked'] == report['files_checked'] == 1


def test_same_layer_removal_leaves_no_archived_key_and_compressed_layer_is_supported(tmp_path):
    report = keys.scan_archive(image(tmp_path, tar_bytes([('app/safe', b'ordinary data')], 'w:gz')))
    assert report['passed'] and not report['findings']


def test_missing_referenced_layer_fails_closed(tmp_path):
    path = tmp_path/'missing.tar'
    path.write_bytes(tar_bytes([('manifest.json', b'[{"Layers":["missing/layer.tar"]}]')]))
    with pytest.raises(ValueError, match='referenced layer'):
        keys.scan_archive(path)


@pytest.mark.parametrize('manifest', [b'[]', b'[{},{}]', b'[{}]', b'[{"Layers":[]}]', b'"text"'])
def test_invalid_image_manifest_fails_closed(tmp_path, manifest):
    path = tmp_path/'invalid.tar'
    path.write_bytes(tar_bytes([('manifest.json', manifest)]))
    with pytest.raises(ValueError):
        keys.scan_archive(path)


def test_cli_never_prints_key_contents(tmp_path, capsys):
    sentinel = b'SYNTHETIC-CONTENT-MUST-NOT-BE-PRINTED'
    path = image(tmp_path, tar_bytes([('etc/ssl/private/ssl-cert-snakeoil.key', sentinel)]))
    assert keys.main(['--archive', str(path)]) == 1
    output = capsys.readouterr()
    assert sentinel.decode() not in output.out + output.err
    assert json.loads(output.out)['passed'] is False


def test_malformed_layer_is_not_a_successful_scan(tmp_path, capsys):
    path = image(tmp_path, b'SYNTHETIC-INVALID-TAR')
    assert keys.main(['--archive', str(path)]) == 2
    output = capsys.readouterr()
    assert 'SYNTHETIC-INVALID-TAR' not in output.out + output.err


def test_large_files_are_read_in_bounded_chunks():
    class Bounded(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= keys.CHUNK_SIZE
            return super().read(size)
    assert not keys.has_private_pem(Bounded(b'x'*(10*keys.CHUNK_SIZE)))


def test_findings_are_bounded_and_paths_cannot_inject_terminal_output(tmp_path, capsys):
    entries = [(f'unsafe\x1b[31m/{i}', pem_header('PRIVATE KEY')+b'\n' + b'Q'*64)
               for i in range(keys.MAX_FINDINGS+5)]
    path = image(tmp_path, tar_bytes(entries))
    assert keys.main(['--archive', str(path)]) == 1
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report['finding_count'] == keys.MAX_FINDINGS+5
    assert len(report['findings']) == keys.MAX_FINDINGS
    assert '\x1b' not in output


def test_dockerfile_removes_generated_key_in_the_installation_layer():
    dockerfile = (Path(__file__).parents[1]/'Dockerfile').read_text()
    instructions = dockerfile.replace('\\\n', ' ').splitlines()
    installation = next(line for line in instructions
                        if line.startswith('RUN ') and 'postgresql-common;' in line)
    assert 'apt-get install -y --no-install-recommends postgresql-17 postgresql-client-17;' in installation
    assert 'rm -f /etc/ssl/private/ssl-cert-snakeoil.key /etc/ssl/certs/ssl-cert-snakeoil.pem;' in installation
    assert installation.index('postgresql-client-17;') < installation.index('rm -f /etc/ssl/private/')
    assert 'test ! -e /etc/ssl/private/ssl-cert-snakeoil.key;' in installation
