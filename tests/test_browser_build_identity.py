"""Exact baked identity checks; synthetic Git/verified archive modes stay distinct."""
import copy
import pytest
from build_identity_support import assert_build_identity


def identity(git):
    return {'revision':'a'*40,'build_identity':('a' if git else 'b')*40,
            'revision_verified':git,'source_kind':'git-head' if git else 'user-provided-zip',
            'built_at':'2026-11-12T00:00:00Z','version':'5.1.8','fingerprint':'c'*64}


@pytest.mark.parametrize('git',[False,True])
def test_exact_identity_from_first_run_supports_both_source_modes(git):
    expected=identity(git)
    assert_build_identity(copy.deepcopy(expected),expected)


@pytest.mark.parametrize('field,value',[('revision','d'*40),('build_identity','d'*40),
                                       ('revision_verified',True),('source_kind','git-head'),
                                       ('built_at','2026-11-12T00:00:01Z')])
def test_mismatched_or_forged_archive_identity_is_not_accepted(field,value):
    expected=identity(False);actual=copy.deepcopy(expected);actual[field]=value
    with pytest.raises(AssertionError):assert_build_identity(actual,expected)


def test_legacy_no_report_path_still_requires_git_and_archive_is_not_forged():
    assert_build_identity(identity(True))
    with pytest.raises(AssertionError):assert_build_identity(identity(False))
