"""Pure, synthetic checks; real container upgrade is a separate explicit CI drill."""
import io
import importlib.util
from pathlib import Path
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
