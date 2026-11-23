import hashlib
import json
import zipfile

import pytest

from scripts import prepare_distribution as delivery
from scripts.test_pillow_relink import validate_relink_image


def test_lgpl_drill_accepts_only_reviewed_source_bound_candidates():
    revision='a'*40;tag='v5.1.10-candidate.'+revision[:7]
    image={'Architecture':'amd64','Os':'linux','Config':{'Labels':{
        'org.opencontainers.image.revision':revision,'org.opencontainers.image.version':tag,
        'org.opencontainers.image.source':'https://github.com/inkzcz/life-journal_public'}}}
    validate_relink_image(tag,image)
    for bad in ('v5.1.11','v5.1.11-candidate.'+revision[:7],'v5.1.10-candidate.'+'b'*7,
                'v5.1.10-candidate.latest','v5.1.9-candidate.invalid'):
        with pytest.raises(ValueError):validate_relink_image(bad,image)
    import copy
    for key,value in (('Architecture','arm64'),('Os','windows')):
        modified=copy.deepcopy(image);modified[key]=value
        with pytest.raises(ValueError):validate_relink_image(tag,modified)
    modified=copy.deepcopy(image);modified['Config']['Labels']['org.opencontainers.image.source']='https://example.invalid'
    with pytest.raises(ValueError):validate_relink_image(tag,modified)


def test_formal_new_version_is_rejected_before_docker_or_source_access(tmp_path,monkeypatch):
    from scripts import test_pillow_relink as relink
    import sys
    monkeypatch.setattr(sys,'argv',['relink','--image-tag','v5.1.11',
        '--sources',str(tmp_path/'not-read'),'--output',str(tmp_path/'not-written')])
    monkeypatch.setattr(relink.local_images,'Docker',lambda:pytest.fail('Unapproved tag must not contact Docker'))
    with pytest.raises(SystemExit) as caught:relink.main()
    assert caught.value.code==2 and not (tmp_path/'not-written').exists()


def test_development_validation_does_not_extend_the_old_release_authorization():
    revision='a'*40
    delivery.require_candidate_identity('v5.1.10-candidate.'+revision[:7],'5.1.10',revision)
    for version in ('v5.1.10','v5.1.9-candidate.'+revision[:7],'v5.1.10-candidate.'+'b'*7):
        with pytest.raises(ValueError,match='source-bound'):
            delivery.require_candidate_identity(version,'5.1.10',revision)
    authority={'binary_publication_approved':True,'repository':'inkzcz/life-journal_public',
        'format':'life-journal-binary-release-authorization-v1','version':'v5.1.9',
        'registry_push_approved':False,'nas_access_approved':False,'private_repository_changes_approved':False,'owner_confirmation_reference':'synthetic approval fixture'}
    delivery.require_release_authorization(authority,'v5.1.9')
    with pytest.raises(ValueError,match='authorization required'):
        delivery.require_release_authorization(authority,'v5.1.10-candidate.'+revision[:7])


def test_deploy_zip_keeps_tagged_inputs_and_legal_texts_with_current_release_guides(tmp_path):
    application=tmp_path/'application';publisher=tmp_path/'publisher'
    tagged=('compose.yaml','.env.example','LICENSE','COPYRIGHT.md')
    guides=tuple('docs/'+n+'.md' for n in ('install','upgrade','backup-restore','known-limitations','upgrade-001'))
    for root in (application,publisher):
        for name in (*tagged,*guides):
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(root.name+': '+name+'\n')
        (root/'.env').write_text('Synthetic configuration must never be included')
    target=tmp_path/'deploy.zip'
    delivery.write_deployment_zip(application,publisher,target)
    with zipfile.ZipFile(target) as archive:
        assert set(archive.namelist())==set(tagged+guides)
        for name in tagged:assert archive.read(name)==(application/name).read_bytes()
        for name in guides:assert archive.read(name)==(publisher/name).read_bytes()


def test_source_tree_must_match_receipts_exactly_and_rejects_injected_files(tmp_path):
    source=tmp_path/'sources/debian/synthetic/source.tar.gz';source.parent.mkdir(parents=True)
    source.write_bytes(b'Synthetic source archive')
    report={'records':[{'files':[{'path':'sources/debian/synthetic/source.tar.gz',
        'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}]}]}
    (tmp_path/'sources.json').write_text(json.dumps(report))
    delivery.verify_source_files(tmp_path,report)
    private=tmp_path/'.env';private.write_text('Synthetic injected configuration')
    with pytest.raises(ValueError,match='Unlisted'):delivery.verify_source_files(tmp_path,report)
    private.unlink();source.write_bytes(b'Modified')
    with pytest.raises(ValueError,match='checksum mismatch'):delivery.verify_source_files(tmp_path,report)


def test_legal_evidence_also_rejects_unlisted_test_or_private_artifacts(tmp_path):
    notice=tmp_path/'legal.txt';notice.write_text('Synthetic public notice')
    data={'notices':[{'path':'legal.txt','sha256':hashlib.sha256(notice.read_bytes()).hexdigest()}],
          'packages':[],'go_modules':[]}
    (tmp_path/'inventory.json').write_text(json.dumps(data))
    delivery.verify_evidence_files(tmp_path,data)
    (tmp_path/'unreviewed.zip').write_bytes(b'Synthetic injected archive')
    with pytest.raises(ValueError,match='Unlisted'):delivery.verify_evidence_files(tmp_path,data)


def test_unverified_or_production_related_receipts_cannot_be_packaged():
    installation={'four_container_health':'passed','ordinary_backup_and_independent_restore':'passed',
        'restart_and_database_persistence':'passed','restored_login':'passed','production_or_nas_accessed':False,
        'lgpl_replacement':{'modified_library_loaded':True,'interface_compatible_query':'passed'}}
    pillow={'modified_lgpl_shim_loaded':True,'library_relinked_from_source':True,'pillow_api_compatible':True}
    layers={'passed':True,'finding_count':0}
    debian={'preserved_legal_texts':410,'browser_packages':43,'psycopg_c_linkage':'libpq.so.5'}
    delivery.require_receipts(installation,pillow,layers,debian)
    for obj,key,value in [(installation,'production_or_nas_accessed',True),
                          (pillow,'library_relinked_from_source',False),(layers,'finding_count',1),
                          (debian,'psycopg_c_linkage','not found')]:
        old=obj[key];obj[key]=value
        with pytest.raises(ValueError,match='receipt failed'):delivery.require_receipts(installation,pillow,layers,debian)
        obj[key]=old


def test_formal_510_has_separate_authority_and_does_not_modify_519_grant():
    from scripts.release_authorization import read_authorization
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    old=read_authorization(root,'v5.1.9');current=read_authorization(root,'v5.1.10')
    assert old['version']=='v5.1.9' and current['version']=='v5.1.10' and current['source_pull_request']==4
    delivery.require_release_authorization(current,'v5.1.10')
    with pytest.raises(ValueError):delivery.require_release_authorization(old,'v5.1.10')
    with pytest.raises(ValueError):delivery.require_release_authorization(current,'v5.1.11')
    for key in ('binary_publication_approved','owner_confirmation_reference','registry_push_approved',
                'nas_access_approved','private_repository_changes_approved','source_pull_request'):
        bad=dict(current);bad.pop(key)
        with pytest.raises(ValueError):delivery.require_release_authorization(bad,'v5.1.10')


def test_same_schema_upgrade_receipt_is_required_and_source_bound():
    version='v5.1.10';revision='a'*40
    report={'synthetic_same_schema_upgrade':'passed','from_version':'5.1.9','to_version':'5.1.10',
        'image_tag':version,'source_commit':revision,'schema_before':'0021_anniversary_calendar',
        'schema_after':'0021_anniversary_calendar','old_backup_created_and_verified':True,
        'existing_article_fields_cards_media_itinerary':'preserved','new_default_type_and_travel_toggles':'passed',
        'candidate_restart_persistence':'passed','production_or_nas_accessed':False}
    delivery.require_upgrade_receipt(report,version,revision)
    for key in report:
        bad=dict(report);bad.pop(key)
        with pytest.raises(ValueError):delivery.require_upgrade_receipt(bad,version,revision)
    for tag,sha in (('v5.1.10-candidate.'+revision[:7],revision),(version,'b'*40)):
        with pytest.raises(ValueError):delivery.require_upgrade_receipt(report,tag,sha)
