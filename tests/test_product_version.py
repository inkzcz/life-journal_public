"""Product mirrors and build labels must agree; no Git/Docker/network required."""
import json
from pathlib import Path
import pytest
from scripts import sync_version as version,local_images
ROOT=Path(__file__).resolve().parents[1]
PRODUCT=version.product_version(ROOT)

def test_actual_product_versions_and_packaged_notes_agree():
    assert version.check(ROOT)==PRODUCT
    from scripts import release_local
    assert release_local.TOOL_VERSION==version.product_version(ROOT)
    notes=json.loads((ROOT/'backend/app/release_notes.json').read_text(encoding='utf-8'))
    assert notes[0]['title'].startswith('v'+version.product_version(ROOT))
    assert '发布状态以GitHub Release为准' in notes[0]['body']

def tree(tmp_path):
    for name in version.mirrors(ROOT):
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text((ROOT/name).read_text(encoding='utf-8'),encoding='utf-8')
    (tmp_path/'VERSION').write_text(version.product_version(ROOT))
    return tmp_path

@pytest.mark.parametrize('name', ['backend/app/version.py','frontend/src/version.ts','frontend/package.json','frontend/package-lock.json','scripts/release_local.py'])
def test_any_mirror_drift_fails_closed(tmp_path,name):
    root=tree(tmp_path);p=root/name;p.write_text(p.read_text().replace(PRODUCT,'0.0.0-drift'))
    with pytest.raises(ValueError,match='mirrors differ'):version.check(root)
    for path,text in version.mirrors(root).items():(root/path).write_text(text)
    assert version.check(root)==PRODUCT

@pytest.mark.parametrize('tag',['v'+PRODUCT,'v'+PRODUCT+'-rc.1','a'*40])
def test_product_tag_prerelease_and_ci_sha_allowed(tag):version.build_tag(tag,ROOT)

@pytest.mark.parametrize('tag',['v0.0.0','v'+PRODUCT+'1','v999.0.0','latest','v'+PRODUCT+'-evil space'])
def test_wrong_tag_rejected_before_docker(tag):
    class NoDocker:
        def run(self,*args):raise AssertionError('No Docker call permitted')
    with pytest.raises(ValueError,match='Image tag must match'):local_images.build(NoDocker(),'a'*40,tag)


@pytest.mark.parametrize('bad',['v5.1.0','5.1','5.1.0;invalid','5.1.0\nother'])
def test_invalid_canonical_version_is_rejected(tmp_path,bad):
    (tmp_path/'VERSION').write_text(bad)
    with pytest.raises(ValueError,match='VERSION must contain'):version.product_version(tmp_path)


def test_cli_build_checks_mirrors_before_git_or_docker(tmp_path,monkeypatch):
    root=tree(tmp_path);p=root/'frontend/src/version.ts';p.write_text(p.read_text().replace(PRODUCT,'0.0.0-drift'))
    monkeypatch.setattr(local_images,'ROOT',root)
    monkeypatch.setattr(local_images,'identify',lambda *a:pytest.fail('Must stop before source/Docker discovery'))
    with pytest.raises(ValueError,match='mirrors differ'):local_images.main(['build','--version','v'+PRODUCT])


def test_delivery_rejects_wrong_product_tag_before_source_or_output(monkeypatch):
    from scripts import release_local
    monkeypatch.setattr(release_local,'identify',lambda *a:pytest.fail('Must stop before source discovery'))
    with pytest.raises(ValueError,match='Image tag must match'):release_local.deliver('v0.0.0')
