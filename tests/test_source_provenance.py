"""Source provenance coverage, attributed geometry, and no automatic license grant."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def materials():
    policy_path = ROOT / 'open_source/policy.json'
    if policy_path.exists():
        from scripts.export_open_source import transform
        policy = json.loads(policy_path.read_text())
        tracked = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z']).decode().split('\0')
        selected = [p for p in tracked if p and (p in policy['include_files'] or
                    any(p.startswith(prefix) for prefix in policy['include_prefixes']))]
        result = {p: transform(p, (ROOT / p).read_bytes(), 'example/life-journal') for p in selected}
        for path in tracked:
            if path.startswith(policy['template_prefix']):
                dest = path[len(policy['template_prefix']):]
                result[dest] = transform(dest, (ROOT / path).read_bytes(), 'example/life-journal')
        return result, 'example/life-journal'
    manifest = json.loads((ROOT / 'EXPORT_MANIFEST.json').read_text())
    return {entry['path']: (ROOT / entry['path']).read_bytes() for entry in manifest['files']}, manifest['target_repository']


def canonical_digest(path, data, repository):
    if not path.startswith('third_party/') and path not in ('LICENSE', 'licensing/GPL-3.0.txt'):
        data = data.replace(repository.encode(), b'__LIFE_JOURNAL_REPOSITORY__')
        data = data.replace(b'example/life-journal', b'__LIFE_JOURNAL_REPOSITORY__')
    return hashlib.sha256(data).hexdigest()


def test_every_delivered_material_has_current_provenance_and_evidence():
    files, repository = materials()
    register = json.loads(files['third_party/source-review.json'])
    entries = {item['path']: item for item in register['files']}
    assert len(entries) == len(register['files']) == len(files)
    assert set(entries) == set(files)
    evidence = {item['id'] for item in register['evidence']}
    for path, data in files.items():
        item = entries[path]
        assert item['evidence'] and set(item['evidence']) <= evidence
        if path == 'third_party/source-review.json':
            assert item['sha256_canonical'] is None and item['classification'] == 'review-metadata'
        else:
            assert item['sha256_canonical'] == canonical_digest(path, data, repository), path
    assert register['review_complete'] is True and register['unresolved'] == []


def test_all_thirteen_geometries_have_fixed_sources_hashes_and_preserved_grants():
    provenance = json.loads((ROOT / 'third_party/icon-provenance.json').read_text())
    text = (ROOT / 'frontend/src/writing/iconPaths.ts').read_text()
    maps = {name: json.loads(value) for name, value in re.findall(r'export const (\w+):Record<string,string>=(\{[^\n]+\})', text)}
    groups = {'module': maps['moduleIconPaths'], 'place': maps['placeIconPaths']}
    assert set(groups['module']) == {'basic', 'body', 'media', 'itinerary', 'relations', 'publish'}
    assert set(groups['place']) == set('lfshtcp')
    assert len(provenance['icons']) == 13
    assert len({(item['group'], item['key']) for item in provenance['icons']}) == 13
    license_text = (ROOT / provenance['license_file']).read_text()
    assert 'ISC License' in license_text and 'The MIT License (MIT)' in license_text
    assert 'Lucide Icons and Contributors' in license_text and 'Cole Bemis' in license_text
    for item in provenance['icons']:
        assert provenance['upstream_commit'] in item['source']
        assert re.fullmatch(r'[0-9a-f]{64}', item['upstream_file_sha256'])
        geometry = groups[item['group']][item['key']]
        assert re.fullmatch(r'[MmLlHhVvCcSsQqTtAaZz0-9.,+\s-]+', geometry)
        assert hashlib.sha256(geometry.encode()).hexdigest() == item['path_sha256']
        assert item['license_file'] == provenance['license_file']
    assert provenance['old_path_origins_proved'] is False


def test_phase_a_activation_is_scoped_and_does_not_approve_publication():
    proposal = json.loads((ROOT / 'licensing/proposal.json').read_text())
    scope = json.loads((ROOT / 'third_party/source-scope.json').read_text())
    declaration = json.loads((ROOT / 'licensing/OWNER_DECLARATION.json').read_text())
    assert proposal['source_third_party_review_complete'] is True
    assert scope['source_third_party_review_complete'] is True
    assert proposal['original_rights_confirmed'] is True
    assert proposal['owner_authorization'] is True and proposal['selected_spdx'] == 'GPL-3.0-or-later'
    assert proposal['owner_authorization_scope'] == 'phase-a-original-source-license-only'
    assert proposal['original_rights_scope'] == 'owner-controlled-protectable-original-source-and-original-increments'
    assert proposal['publication_approved'] is False and scope['publication_approved'] is False
    assert scope['license_effective'] is True and scope['third_party_relicensed'] is False
    assert declaration['publication_approved'] is False and declaration['all_third_party_rights_reviewed'] is False
    assert declaration['proposed_copyright_notice'] == 'Copyright (C) 2026 inkzcz'
    assert (ROOT / 'LICENSE').is_file() and (ROOT / 'COPYRIGHT.md').is_file()
