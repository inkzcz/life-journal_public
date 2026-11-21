"""Synthetic phase B records test binding; no real public operation is performed."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
from scripts import open_source_gate as gate

ROOT=Path(__file__).resolve().parents[1]
REPOSITORY='example/phase-b-source'


def manifest(root):
    entries=[{'path':p.relative_to(root).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted(root.rglob('*')) if p.is_file() and p.name!='EXPORT_MANIFEST.json']
    data={'format':'life-journal-public-source-v1','candidate_version':'5.1.9',
          'source_commit':'a'*40,'target_repository':REPOSITORY,'distribution_scope':'source-only',
          'publication_approved':False,'license_activation_approved':True,
          'original_git_history_included':False,'binary_artifacts_included':False,'files':entries}
    (root/'EXPORT_MANIFEST.json').write_text(json.dumps(data,indent=2)+'\n')


@pytest.fixture
def licensed(tmp_path):
    root=tmp_path/'source';(root/'licensing').mkdir(parents=True)
    for name in ['LICENSE','COPYRIGHT.md','licensing/GPL-3.0.txt','licensing/proposal.json',
                 'licensing/PHASE_A_AUTHORIZATION.json']:
        (root/name).write_bytes((ROOT/name).read_bytes())
    # These are schema fixtures, not new declarations or signatures by the owner.
    path=root/'licensing/PHASE_A_AUTHORIZATION.json';data=json.loads(path.read_text())
    data['basis']='Synthetic unit fixture only, not a real authorization';path.write_text(json.dumps(data))
    (root/'README.md').write_text('Synthetic licensed fixture\n');manifest(root)
    return root


def approval(root,path,**changes):
    raw=(root/'EXPORT_MANIFEST.json').read_bytes();m=json.loads(raw)
    data={'format':'life-journal-publication-approval-v1','phase':'B','publication_approved':True,
          'scope':'clean-source-snapshot-only','repository':REPOSITORY,
          'source_commit':m['source_commit'],'manifest_sha256':hashlib.sha256(raw).hexdigest(),
          'source_tree_sha256':hashlib.sha256(gate.snapshot_checksums(root)).hexdigest(),
          'hash_definition':'sha256sums-lf-includes-export-manifest-v1',
          'owner_confirmation_reference':'Synthetic test only, not actual owner approval'}
    data.update(changes);path.write_text(json.dumps(data));return path


def check(root,path=None):
    return gate.scan(root,snapshot=True,require_publication=True,approval_file=path,
                     publication_repository=REPOSITORY)


def test_phase_a_export_license_passes_but_missing_or_pending_b_is_denied(licensed,tmp_path):
    assert gate.scan(licensed,snapshot=True,require_license=True)['passed']
    assert not check(licensed)['passed']
    pending=approval(licensed,tmp_path/'pending.json',publication_approved=False)
    report=check(licensed,pending)
    assert not report['passed']
    assert any(f.get('reason')=='phase-b-owner-approval-pending' for f in report['findings'])


def test_synthetic_b_accepts_only_bound_bytes_without_publishing_anything(licensed,tmp_path):
    record=approval(licensed,tmp_path/'synthetic-b.json')
    assert check(licensed,record)['passed']
    assert not (licensed/'.git').exists()


@pytest.mark.parametrize('changes',[
    {'publication_approved':False},{'phase':'A'},{'repository':'example/other'},
    {'source_commit':'b'*40},{'manifest_sha256':'c'*64},{'source_tree_sha256':'d'*64},
    {'scope':'binary-release'},{'owner_confirmation_reference':None},
    {'hash_definition':'unrelated-hash'},
])
def test_wrong_destination_identity_hash_or_scope_is_denied(licensed,tmp_path,changes):
    assert not check(licensed,approval(licensed,tmp_path/'invalid.json',**changes))['passed']


def test_self_declared_publication_field_never_replaces_external_b(licensed,tmp_path):
    path=licensed/'licensing/proposal.json';data=json.loads(path.read_text())
    data['publication_approved']=True;path.write_text(json.dumps(data));manifest(licensed)
    record=approval(licensed,tmp_path/'pending.json',publication_approved=False)
    assert not check(licensed,record)['passed']


@pytest.mark.parametrize('rebuild_manifest',[False,True])
def test_changed_source_needs_new_approval_even_if_manifest_is_regenerated(licensed,tmp_path,rebuild_manifest):
    record=approval(licensed,tmp_path/'bound.json')
    (licensed/'README.md').write_text('Changed bytes\n')
    if rebuild_manifest:manifest(licensed)
    assert not check(licensed,record)['passed']


@pytest.mark.parametrize('changes',[{'source_commit':None},{'source_commit':'not-a-sha'},{'format':'other'}])
def test_invalid_manifest_identity_cannot_be_approved_as_source(licensed,tmp_path,changes):
    path=licensed/'EXPORT_MANIFEST.json';data=json.loads(path.read_text());data.update(changes)
    path.write_text(json.dumps(data))
    assert not check(licensed,approval(licensed,tmp_path/'bound.json'))['passed']


@pytest.mark.parametrize('name',['LICENSE','COPYRIGHT.md','licensing/PHASE_A_AUTHORIZATION.json'])
def test_flags_cannot_replace_license_notice_and_phase_a_record(licensed,tmp_path,name):
    (licensed/name).unlink();manifest(licensed)
    assert not gate.scan(licensed,snapshot=True,require_license=True)['passed']
    assert not check(licensed,approval(licensed,tmp_path/'bound.json'))['passed']


def test_b_record_inside_snapshot_is_rejected(licensed):
    record=approval(licensed,licensed/'approval.json');manifest(licensed)
    assert not check(licensed,record)['passed']


def test_publication_cli_returns_nonzero_for_pending_b(licensed,tmp_path):
    record=approval(licensed,tmp_path/'pending.json',publication_approved=False)
    result=subprocess.run([sys.executable,str(ROOT/'scripts/open_source_gate.py'),'--root',str(licensed),
        '--snapshot','--require-publication','--approval-file',str(record),
        '--publication-repository',REPOSITORY],capture_output=True,text=True,timeout=10)
    assert result.returncode==1
    assert any(f['type']=='phase-b-publication-not-approved' for f in json.loads(result.stdout)['findings'])


def test_current_real_phase_b_record_is_still_unapproved():
    # The private branch has a pending record. Exported snapshots keep the same
    # explicit historical stage status in proposal.json, with no external B file.
    assert json.loads((ROOT/'licensing/proposal.json').read_text())['publication_approved'] is False
    path=ROOT/'open_source/publication-approval.json'
    if path.exists():assert json.loads(path.read_text())['publication_approved'] is False
