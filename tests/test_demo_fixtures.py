"""Synthetic package generation must leave a read-only source tree untouched."""
from pathlib import Path
from scripts.demo_fixtures import example_bytes


def test_example_bytes_does_not_create_source_artifacts(tmp_path):
    source=Path(__file__).resolve().parents[1]
    example=tmp_path/'docs/v5.1.5/examples/travel.json'
    example.parent.mkdir(parents=True)
    example.write_bytes((source/'docs/v5.1.5/examples/travel.json').read_bytes())
    before={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    first=example_bytes(tmp_path)
    assert first==example_bytes(tmp_path) and first.startswith(b'PK')
    assert {p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}==before
