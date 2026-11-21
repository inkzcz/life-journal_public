"""Pure build identity assertion from the candidate browser probe."""
def assert_build_identity(info, expected=None):
    import re
    assert re.fullmatch('[0-9a-f]{40}', info['revision'])
    assert re.fullmatch('[0-9a-f]{40}', info['build_identity'])
    assert type(info['revision_verified']) is bool
    assert info['source_kind'] == ('git-head' if info['revision_verified'] else 'user-provided-zip')
    assert info['built_at'].endswith('Z')
    if expected is None:
        assert info['revision_verified'] is True
    else:
        assert {k: v for k, v in info.items() if k != 'changelog'} == expected
