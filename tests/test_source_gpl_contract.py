"""Source-only GPL proposal and unchanged production lunar semantics."""
import hashlib
import json
from datetime import date
from pathlib import Path
import sys
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


def test_gpl_candidate_is_verbatim_and_does_not_grant_owner_rights():
    proposal=json.loads((ROOT/'licensing/proposal.json').read_text())
    raw=(ROOT/'licensing/GPL-3.0.txt').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==proposal['license_text_sha256']
    assert raw==(ROOT/'third_party/licenses/lunardate-GPL-3.0.txt').read_bytes()
    assert proposal['proposed_spdx']=='GPL-3.0-or-later'
    assert proposal['third_party_relicensed'] is False
    assert proposal['current_combination_license_version']==3
    assert proposal['future_combination_compatibility_guaranteed'] is False
    assert proposal['state'] in ('pending-owner-confirmation','owner-confirmed')
    if proposal['state']=='pending-owner-confirmation':
        assert proposal['owner_authorization'] is False and proposal['original_rights_confirmed'] is False
        assert proposal['selected_spdx'] is None and not (ROOT/'LICENSE').exists()
    else:
        assert proposal['owner_authorization'] and proposal['original_rights_confirmed']
        assert (ROOT/'LICENSE').is_file()
        from scripts.open_source_gate import license_materials_confirmed
        assert license_materials_confirmed(ROOT)
        assert proposal['publication_approved'] is False
        notice=(ROOT/'COPYRIGHT.md').read_text()
        assert 'DRAFT' not in notice and 'proposed' not in notice.lower()
        assert 'original increments' in notice and 'Third-party' in notice


def test_historical_declaration_is_preserved_and_phase_a_is_a_separate_record():
    declaration=json.loads((ROOT/'licensing/OWNER_DECLARATION.json').read_text())
    proposal=json.loads((ROOT/'licensing/proposal.json').read_text())
    assert declaration['personal_project_lead_declared'] is True
    assert declaration['sole_human_developer_declared'] is True
    assert declaration['other_developers_declared'] is False
    assert declaration['company_or_employer_code_declared'] is False
    assert declaration['public_copyright_holder']=='inkzcz'
    assert declaration['proposed_copyright_notice']=='Copyright (C) 2026 inkzcz'
    assert declaration['preferred_spdx']=='GPL-3.0-or-later'
    assert declaration['all_third_party_rights_reviewed'] is False
    assert declaration['final_license_authorization'] is False
    assert declaration['publication_approved'] is False
    assert proposal['owner_declaration_received'] is True
    record=json.loads((ROOT/'licensing/PHASE_A_AUTHORIZATION.json').read_text())
    assert record['phase']=='A' and record['approved'] is True
    assert record['publication_approved'] is False
    assert record['historical_owner_declaration_sha256']==hashlib.sha256((ROOT/'licensing/OWNER_DECLARATION.json').read_bytes()).hexdigest()
    assert 'Copyright (C) 2026 inkzcz' in (ROOT/'licensing/ORIGINAL_CODE_NOTICE.DRAFT.txt').read_text()
    assert (ROOT/'licensing/ORIGINAL_CODE_NOTICE.DRAFT.txt').read_text().startswith('DRAFT ONLY')


def test_source_manifest_excludes_binaries_runtime_data_and_history():
    path=ROOT/'EXPORT_MANIFEST.json'
    if not path.exists():
        pytest.skip('Snapshot-only assertion; exercised against the exported source')
    manifest=json.loads(path.read_text())
    assert manifest['distribution_scope']=='source-only'
    assert manifest['binary_artifacts_included'] is False
    assert manifest['original_git_history_included'] is False
    # The pristine export has no .git. After the owner initializes a NEW public
    # history, its own .git is legitimate; original baseline objects must not
    # have been imported. Snapshot scanning still rejects any .git in delivery.
    if (ROOT/'.git').exists():
        for baseline in (manifest.get('feature_baseline'),manifest.get('preparation_baseline')):
            if baseline:
                result=subprocess.run(['git','-C',str(ROOT),'cat-file','-e',baseline+'^{commit}'],
                                      stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                assert result.returncode!=0,'Original private history must not enter the new repository'
    forbidden={'.tar','.zip','.exe','.dll','.so','.pyc','.jpg','.png','.mp4','.db','.dump'}
    assert all(Path(item['path']).suffix.lower() not in forbidden for item in manifest['files'])
    assert all('.git' not in Path(item['path']).parts for item in manifest['files'])


@pytest.mark.parametrize('year,month,day,leap,expected',[
    (1933,5,30,True,None),(1954,10,30,False,date(1954,11,25)),
    (1978,7,30,False,None),(2057,8,30,False,None),
    (2024,1,1,False,date(2024,2,10)),(2025,1,1,False,date(2025,1,29)),
])
def test_original_lunar_behavior_is_preserved(year,month,day,leap,expected):
    from app.calendar.dates import DateRule,occurrence,LunarDate
    assert LunarDate.__module__=='lunardate'
    if expected is None:
        with pytest.raises(ValueError):
            DateRule(calendar='lunar',year=year,month=month,day=day,leap_month=leap)
    else:
        rule=DateRule(calendar='lunar',year=year,month=month,day=day,leap_month=leap)
        assert occurrence(rule,year)==expected
