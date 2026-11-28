"""Version-specific owner authorization; historical grants stay immutable."""
import json
import hashlib
from pathlib import Path
import re

REPOSITORY = 'inkzcz/life-journal_public'
RELEASES = {
    'v5.1.12': ('licensing/BINARY_RELEASE_v5.1.12_SOURCE_BINDING_AUTHORIZATION.json', 11),
    'v5.1.9': ('licensing/BINARY_RELEASE_AUTHORIZATION.json', 2),
    'v5.1.11': ('licensing/BINARY_RELEASE_v5.1.11_REPAIR_AUTHORIZATION.json', 9),
    'v5.1.10': ('licensing/BINARY_RELEASE_v5.1.10_AUTHORIZATION.json', 4),
}


def release_version(version):
    match = re.fullmatch(r'(v\d+\.\d+\.\d+)(?:-candidate\.[0-9a-f]{7,40})?', version)
    if not match or match[1] not in RELEASES:
        raise ValueError('Only an explicitly owner-authorized release is accepted')
    return match[1]


def read_authorization(root, version):
    version = release_version(version)
    path = Path(root) / RELEASES[version][0]
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('Authorization must be a regular local source file')
    authority = json.loads(path.read_text())
    validate_authorization(authority, version)
    if version in ('v5.1.11','v5.1.12'):
        prior = Path(root) / authority['previous_authorization']
        if (prior.is_symlink() or any(p.is_symlink() for p in prior.parents)
                or hashlib.sha256(prior.read_bytes()).hexdigest() != authority['previous_authorization_sha256']):
            raise ValueError('Original owner authorization must remain unchanged')
        if version == 'v5.1.12':
            original = json.loads(prior.read_text())
            _validate_grant(original, version)
            if original.get('source_pull_request') != 10 or 'unreleased_tag_repair' in original:
                raise ValueError('Original normal v5.1.12 authorization required')
    return authority


def _validate_grant(authority, version):
    if (not isinstance(authority, dict) or authority.get('format') != 'life-journal-binary-release-authorization-v1'
            or authority.get('version') != version
            or authority.get('repository') != REPOSITORY
            or authority.get('binary_publication_approved') is not True
            or authority.get('registry_push_approved') is not False
            or authority.get('nas_access_approved') is not False
            or authority.get('private_repository_changes_approved') is not False
            or not authority.get('owner_confirmation_reference')):
        raise ValueError('Separate owner binary-release authorization required')


def validate_authorization(authority, version):
    version = release_version(version)
    _validate_grant(authority, version)
    if version in ('v5.1.10','v5.1.11','v5.1.12') and authority.get('source_pull_request') != RELEASES[version][1]:
        raise ValueError('Authorized source PR mismatch')
    if version == 'v5.1.12':
        binding = authority.get('source_binding_supplement', {})
        if not isinstance(binding, dict):
            raise ValueError('Normal source-binding metadata must be an object')
        if (authority.get('previous_authorization') != 'licensing/BINARY_RELEASE_v5.1.12_AUTHORIZATION.json'
                or authority.get('previous_authorization_sha256') != '515baf83a861c1804c82b9ae94370dba7a0e689aadf24907fec452ef6bdfca06'
                or binding.get('scope') != 'normal-release-source-correction'
                or binding.get('previous_source_pull_request') != 10
                or binding.get('previous_merge_commit') != '13df85a6cff538c57528cff4b56de4384dbc6a5f'
                or binding.get('tag_repair_approved') is not False
                or binding.get('historical_tag_replacement_approved') is not False
                or authority.get('reviewed_main_baseline') != binding.get('previous_merge_commit')
                or not re.fullmatch('[0-9a-f]{40}', authority.get('reviewed_feature_head', ''))
                or 'unreleased_tag_repair' in authority or 'retained_tag_identity' in authority):
            raise ValueError('Exact normal v5.1.12 source-binding supplement required')
    if version == 'v5.1.11':
        repair = authority.get('unreleased_tag_repair', {})
        if (repair.get('approved') is not True or repair.get('one_time') is not True
                or repair.get('published_tag_replacement_approved') is not False
                or repair.get('original_tag_sha') != '953a945b48dd8c11639f90ac62c2361b421469ab'
                or repair.get('original_source_commit') != '3c3a465e5ba1dd353a3886b6394907311e972865'
                or authority.get('previous_authorization') != 'licensing/BINARY_RELEASE_v5.1.11_AUTHORIZATION.json'
                or authority.get('previous_authorization_sha256') != '73958921028dc910b7d423d1c5cc610a2c441d641f5d83f327656ddd3a4fc8a7'
                or authority.get('reviewed_feature_head') != '9748cf4324fe8c1e938057e5b5e4296e7dc9fdf7'):
            raise ValueError('Exact one-time unreleased v5.1.11 repair authority required')
    return version
