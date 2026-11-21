"""The maintained source manifest must cover exact tracked bytes, not caches."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def test_current_inventory_covers_every_tracked_payload_and_hash():
    manifest=json.loads((ROOT/'EXPORT_MANIFEST.json').read_text())
    tracked=set(subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z']).decode().split('\0'))-{''}
    expected={entry['path']:entry['sha256'] for entry in manifest['files']}
    assert len(expected)==len(manifest['files'])
    assert set(expected)==tracked-{'EXPORT_MANIFEST.json'}
    for name,digest in expected.items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
