"""Synthetic credential shapes only, constructed at runtime and never echoed."""
import json
import hashlib
from pathlib import Path
import subprocess
import sys

import pytest
from scripts import open_source_gate as gate


@pytest.mark.parametrize('clearance,expected',[(None,False),(False,False),(True,True)])
def test_personal_declaration_does_not_replace_source_clearance(clearance,expected):
    # Synthetic state only: a historical statement cannot supply final clearance.
    proposed={'state':'owner-confirmed','owner_authorization':True,
              'original_rights_confirmed':True,'selected_spdx':'GPL-3.0-or-later',
              'owner_declaration_received':True,'owner_authorization_scope':gate.PHASE_A_SCOPE,
              'original_rights_scope':gate.ORIGINAL_RIGHTS_SCOPE,'publication_approved':False}
    if clearance is not None:
        proposed['source_third_party_review_complete']=clearance
    assert gate.license_proposal_confirmed(json.dumps(proposed)) is expected


def test_license_text_does_not_silently_approve_pending_owner_rights(tmp_path):
    (tmp_path/'LICENSE').write_text('Synthetic test text, not an actual grant')
    folder=tmp_path/'licensing';folder.mkdir()
    (folder/'proposal.json').write_text(json.dumps({'state':'pending-owner-confirmation',
        'owner_authorization':False,'original_rights_confirmed':False,'selected_spdx':None}))
    report=gate.scan(tmp_path,snapshot=True,require_license=True)
    assert any(f['type']=='owner-rights-confirmation-pending' for f in report['findings'])


def test_public_copyright_exception_is_exact_and_keeps_secret_checks(tmp_path):
    name='third_party/licenses/synthetic.txt'
    text=b'Copyright Synthetic Author <public-credit@'+b'upstream.invalid-domain.org>\n'
    target=tmp_path/name;target.parent.mkdir(parents=True);target.write_bytes(text)
    index=tmp_path/'third_party/notice-index.json'
    index.write_text(json.dumps({'format':'life-journal-reviewed-notices-v1','files':[
        {'path':name,'sha256':hashlib.sha256(text).hexdigest()}]}))
    assert gate.scan(tmp_path,snapshot=True)['passed']
    target.write_bytes(text+b'changed')
    report=gate.scan(tmp_path,snapshot=True)
    assert {f['type'] for f in report['findings']} >= {'personal-email-needs-review','changed-public-copyright-notice'}
    secret=('gh'+'p_'+'Q'*36).encode()
    assert any(f['type']=='github-token' for f in gate.scan_bytes(name,text+secret,reviewed_copyright=True))


def test_copyright_registry_cannot_allow_personal_app_data(tmp_path):
    index=tmp_path/'third_party/notice-index.json';index.parent.mkdir()
    index.write_text(json.dumps({'format':'life-journal-reviewed-notices-v1','files':[
        {'path':'backend/app/private.py','sha256':'a'*64}]}))
    assert any(f['type']=='invalid-public-notice-index' for f in gate.scan(tmp_path,snapshot=True)['findings'])


def test_standalone_snapshot_gate_does_not_create_bytecode_or_modify_inputs(tmp_path):
    source=Path(__file__).resolve().parents[1]
    scripts=tmp_path/'scripts';scripts.mkdir()
    for name in ('open_source_gate.py','image_private_keys.py','__init__.py'):
        (scripts/name).write_bytes((source/'scripts'/name).read_bytes())
    before={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result=subprocess.run([sys.executable,str(scripts/'open_source_gate.py'),'--root',str(tmp_path),'--snapshot'],
                          cwd=tmp_path,capture_output=True,text=True,timeout=10)
    assert result.returncode==0
    assert json.loads(result.stdout)['passed']
    assert {p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}==before


@pytest.mark.parametrize('name',['.env','.env.nas','private/key.pem','data/database.sql',
                                'db.sqlite3','backup/copy.txt','media/portrait.jpg','dump.tar',
                                'docs/screen.png','font.woff2','backend/__pycache__/a.pyc',
                                'video.mp4','native/module.so.1','wheel.whl','app.exe','module.wasm'])
def test_sensitive_paths_are_blocked(name):
    assert gate.scan_bytes(name,b'synthetic content')


def test_examples_require_empty_secret_fields():
    assert not gate.scan_bytes('.env.example',b'POSTGRES_PASSWORD=\nSETUP_KEY=\n')
    assert gate.scan_bytes('.env.example',b'POSTGRES_PASSWORD='+b'Q'*24+b'\n')


@pytest.mark.parametrize('prefix,size',[('gh'+'p_',36),('github'+'_pat_',60),('sk'+'-proj-',48),('tskey'+'-auth-',40)])
def test_known_token_shapes_fail_without_returning_values(prefix,size):
    value=(prefix+'Q'*size).encode()
    result=gate.scan_bytes('config.py',b'value='+value)
    assert result and value.decode() not in json.dumps(result)


def test_key_material_detected_across_blocks():
    data=b'-----BEGIN '+b'PRIVATE KEY-----\n'+b'Q'*64+b'\n-----END PRIVATE KEY-----'
    assert any(x['type']=='private-key-material' for x in gate.scan_bytes('config.txt',data))


def test_real_address_shape_requires_review_but_reserved_examples_do_not():
    value=('someone'+'@'+'private-domain'+'.com').encode()
    result=gate.scan_bytes('README.md',value)
    assert result and value.decode() not in json.dumps(result)
    assert not gate.scan_bytes('README.md',b'fixture@example.invalid')


@pytest.mark.parametrize('data',[b'on: pull_request_target',b'permissions: write-all',
                                b'permissions:\n  contents: write',b'run: printenv',
                                b'run: gh repo create synthetic',b'uses: actions/upload-artifact@v4'])
def test_unsafe_workflow_patterns_are_blocked(data):
    assert gate.scan_bytes('.github/workflows/check.yml',data)


def test_binary_workflow_exception_is_owner_scoped_and_byte_exact(tmp_path):
    path=tmp_path/'.github/workflows/ci.yml';path.parent.mkdir(parents=True)
    raw=b'permissions:\n  contents: read\nuses: actions/upload-artifact@synthetic\n'
    path.write_bytes(raw)
    authority={'format':'life-journal-binary-release-authorization-v1','binary_publication_approved':True,
        'repository':'inkzcz/life-journal_public','version':'v5.1.9',
        'registry_push_approved':False,'nas_access_approved':False,'owner_confirmation_reference':'Synthetic owner fixture',
        'technically_reviewed_workflows':{'.github/workflows/ci.yml':{'scope':'candidate-artifacts','sha256':hashlib.sha256(raw).hexdigest()}}}
    (tmp_path/'licensing').mkdir();record=tmp_path/'licensing/BINARY_RELEASE_AUTHORIZATION.json'
    record.write_text(json.dumps(authority))
    allowed=gate.reviewed_binary_workflows(tmp_path)
    assert allowed=={'.github/workflows/ci.yml':'candidate-artifacts'}
    assert not gate.scan_bytes('.github/workflows/ci.yml',raw,binary_workflow_scope=allowed['.github/workflows/ci.yml'])
    for forbidden in (b'contents: write',b'packages: write',b'docker push synthetic',b'gh release create synthetic',b'pull_request_target',b'run: printenv'):
        assert gate.scan_bytes('.github/workflows/ci.yml',forbidden,binary_workflow_scope='candidate-artifacts')
    path.write_bytes(raw+b'changed')
    assert gate.reviewed_binary_workflows(tmp_path)=={}
    path.write_bytes(raw);authority['binary_publication_approved']=False;record.write_text(json.dumps(authority))
    assert gate.reviewed_binary_workflows(tmp_path)=={}


def test_snapshot_rejects_history_symlinks_and_license_omission(tmp_path):
    (tmp_path/'README.md').write_text('synthetic public source')
    (tmp_path/'.git').mkdir()
    result=gate.scan(tmp_path,snapshot=True,require_license=True)
    assert {x['type'] for x in result['findings']}=={'git-history-or-symlink','owner-license-decision-pending'}


def test_snapshot_does_not_follow_symlinks(tmp_path):
    target=tmp_path/'target';target.write_text('synthetic')
    try:(tmp_path/'link').symlink_to(target)
    except OSError:pytest.skip('Symlink creation unavailable on this platform')
    assert any(x['type']=='symlink' for x in gate.scan(tmp_path,snapshot=True)['findings'])


def test_cli_output_is_locations_only(tmp_path,capsys):
    value='gh'+'p_'+'Q'*36
    (tmp_path/'unsafe.py').write_text(value)
    assert gate.main(['--root',str(tmp_path),'--snapshot'])==1
    output=capsys.readouterr()
    assert value not in output.out+output.err
    assert json.loads(output.out)['finding_count']==1


def test_snapshot_manifest_rejects_extra_files_and_changed_content(tmp_path):
    (tmp_path/'README.md').write_text('reviewed source')
    manifest={'files':[{'path':'README.md','sha256':hashlib.sha256(b'reviewed source').hexdigest()}]}
    (tmp_path/'EXPORT_MANIFEST.json').write_text(json.dumps(manifest))
    assert gate.scan(tmp_path,snapshot=True)['passed']
    (tmp_path/'extra.txt').write_text('unreviewed')
    (tmp_path/'README.md').write_text('changed')
    result=gate.scan(tmp_path,snapshot=True)
    assert {x['type'] for x in result['findings']}=={'unlisted-export-file','export-hash-mismatch'}


def test_publisher_supplement_is_exactly_bound_and_does_not_rewrite_owner_grant(tmp_path):
    import copy
    root=Path(__file__).resolve().parents[1]
    version='v5.1.11';name='licensing/BINARY_RELEASE_v5.1.11_AUTHORIZATION.json'
    original=(root/name).read_bytes();review=json.loads((root/'licensing/v5.1.11-release-orchestration-review.json').read_bytes())
    folder=tmp_path/'licensing';folder.mkdir();target=folder/'v5.1.11-release-orchestration-review.json'
    target.write_text(json.dumps(review))
    assert gate.orchestration_workflow_reviews(tmp_path,version,name,original)==review['workflows']
    for key,value in [('original_authorization_sha256','0'*64),('annotated_tag_sha','0'*40),('technical_review_only',False),('application_source_commit','0'*40),('version','v5.1.12'),('application_pull_request',6)]:
        wrong=copy.deepcopy(review);wrong[key]=value;target.write_text(json.dumps(wrong))
        assert gate.orchestration_workflow_reviews(tmp_path,version,name,original)=={}
    target.write_text(json.dumps(review));assert gate.orchestration_workflow_reviews(tmp_path,version,name,original+b'changed')=={}
    assert (root/name).read_bytes()==original
