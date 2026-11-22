"""Pure, synthetic checks; real container upgrade is a separate explicit CI drill."""
import io
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import pytest
from PIL import Image

path=Path(__file__).with_name('docker_same_schema_upgrade.py')
spec=importlib.util.spec_from_file_location('same_schema_drill',path)
drill=importlib.util.module_from_spec(spec);spec.loader.exec_module(drill)


def test_generated_upgrade_photo_is_valid_and_contains_no_external_media():
    with Image.open(io.BytesIO(drill.synthetic_png())) as picture:
        picture.load()
        assert picture.size==(8,8) and picture.format=='PNG' and not picture.getexif()


def test_unreviewed_previous_image_bytes_are_rejected_before_docker_loading(tmp_path):
    archive=tmp_path/'synthetic-invalid.tar';archive.write_bytes(b'Synthetic incorrect TAR, not a Docker image')
    with pytest.raises(ValueError,match='checksum mismatch'):
        drill.verify_previous_tar(archive)


@pytest.fixture
def oci_archive(tmp_path,monkeypatch):
    config={'architecture':'amd64','os':'linux','config':{'Labels':{
        'org.opencontainers.image.revision':drill.OLD_SOURCE,'org.opencontainers.image.version':drill.OLD_TAG}},
        'rootfs':{'type':'layers','diff_ids':[]}}
    raw=json.dumps(config).encode();config_id='sha256:'+hashlib.sha256(raw).hexdigest()
    parent=json.dumps({'schemaVersion':2,'config':{'digest':config_id},'layers':[]}).encode()
    parent_id='sha256:'+hashlib.sha256(parent).hexdigest()
    index=json.dumps({'schemaVersion':2,'manifests':[{'digest':parent_id}]}).encode()
    index_id='sha256:'+hashlib.sha256(index).hexdigest()
    files={'config.json':raw,'index.json':index,'blobs/sha256/'+parent_id.split(':')[1]:parent,
        'manifest.json':json.dumps([{'Config':'config.json','RepoTags':['life-journal:'+drill.OLD_TAG],'Layers':[]}]).encode()}
    archive=tmp_path/'synthetic-previous.tar'
    with tarfile.open(archive,'w') as out:
        for name,data in files.items():
            info=tarfile.TarInfo(name);info.size=len(data);out.addfile(info,io.BytesIO(data))
    # Synthetic archives exercise the same integrity logic without a real release
    # image, Docker daemon, credential, database or production resource.
    monkeypatch.setattr(drill,'OLD_TAR_SHA256',hashlib.sha256(archive.read_bytes()).hexdigest())
    return archive,config,config_id,parent_id,index_id


class Store:
    def __init__(self,config,identity,existing=None):
        self.loads=0;self.identity=identity;self.config=config;self.existing=existing
    def run(self,*args):
        if args[:3]==('docker','image','inspect'):
            if self.existing is None:raise subprocess.CalledProcessError(1,args,stderr='No such image')
            return json.dumps([self.existing])
        if args[:2]==('docker','load'):
            self.loads+=1
            self.existing={'Id':self.identity,'Architecture':'amd64','Os':'linux',
                'Config':self.config['config'],'RootFS':{'Layers':self.config['rootfs']['diff_ids']}}
            return ''
        if args[:3]==('docker','image','ls'):return self.identity
        raise AssertionError('Unexpected Docker command type')


@pytest.mark.parametrize('identity_index',[2,3,4])
def test_load_proves_config_and_oci_store_identities_with_repeated_import(oci_archive,identity_index):
    archive,config,config_id,*_=oci_archive
    commands=Store(config,oci_archive[identity_index])
    assert drill.load_previous_image(archive,commands)==config_id
    assert commands.loads==2


def test_unrelated_loaded_id_is_not_accepted_as_an_oci_identity(oci_archive):
    archive,config,*_=oci_archive
    commands=Store(config,'sha256:'+'f'*64)
    with pytest.raises(ValueError,match='Loaded image identity/config differs'):
        drill.load_previous_image(archive,commands)


def test_existing_conflict_is_rejected_before_any_import(oci_archive):
    archive,config,*_=oci_archive
    commands=Store(config,'sha256:'+'f'*64,{'Id':'sha256:'+'f'*64,'Config':config['config']})
    with pytest.raises(ValueError,match='conflicts with archive'):
        drill.load_previous_image(archive,commands)
    assert commands.loads==0
