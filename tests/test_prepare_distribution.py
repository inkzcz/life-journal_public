import hashlib
import json

import pytest

from scripts import prepare_distribution as delivery


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
