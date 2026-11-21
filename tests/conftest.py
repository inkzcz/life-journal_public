"""Generate only owned, synthetic fixture bytes in this test checkout."""
from pathlib import Path
import sys


def pytest_sessionstart(session):
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    from scripts.demo_fixtures import prepare
    prepare(root)
