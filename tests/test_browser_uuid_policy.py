"""Business identities must use the secure HTTP-compatible helper."""
from pathlib import Path
import re

def test_browser_business_code_has_no_direct_random_uuid_calls():
    root=Path(__file__).resolve().parents[1]/'frontend/src'
    offenders=[]
    for path in root.rglob('*'):
        if path.suffix not in ('.ts','.vue') or path.name.endswith('.test.ts') or path==root/'ids.ts':continue
        if re.search(r'\bcrypto\s*\.\s*randomUUID\s*\(',path.read_text()):offenders.append(str(path.relative_to(root)))
    assert not offenders,offenders
    assert not re.search(r'\bMath\s*\.\s*random\s*\(', (root/'ids.ts').read_text())
