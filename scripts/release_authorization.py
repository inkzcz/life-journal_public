"""Version-specific owner authorization; historical grants stay immutable."""
import json
from pathlib import Path
import re

REPOSITORY = 'inkzcz/life-journal_public'
RELEASES = {
    'v5.1.9': ('licensing/BINARY_RELEASE_AUTHORIZATION.json', 2),
    'v5.1.11': ('licensing/BINARY_RELEASE_v5.1.11_AUTHORIZATION.json', 5),
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
    return authority


def validate_authorization(authority, version):
    version = release_version(version)
    if (authority.get('format') != 'life-journal-binary-release-authorization-v1'
            or authority.get('version') != version
            or authority.get('repository') != REPOSITORY
            or authority.get('binary_publication_approved') is not True
            or authority.get('registry_push_approved') is not False
            or authority.get('nas_access_approved') is not False
            or authority.get('private_repository_changes_approved') is not False
            or not authority.get('owner_confirmation_reference')):
        raise ValueError('Separate owner binary-release authorization required')
    if version in ('v5.1.10','v5.1.11') and authority.get('source_pull_request') != RELEASES[version][1]:
        raise ValueError('Authorized source PR mismatch')
    return version
