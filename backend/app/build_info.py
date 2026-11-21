"""Whitelisted baked metadata, never arbitrary runtime environment or GitHub calls."""
import hashlib,json,re
from datetime import datetime
from pathlib import Path
from .version import __version__
METADATA=Path(__file__).resolve().parents[1]/'BUILD_INFO.json'
NOTES=Path(__file__).with_name('release_notes.json')
def build_info(admin=False):
    result={'version':__version__,'short_revision':None,'built_at':None,'revision_verified':False,'source_kind':'unversioned','fingerprint':None}
    try:
        data=json.loads(METADATA.read_text(encoding='utf-8'))
        revision=data['revision'];identity=data['build_identity'];verified=data['revision_verified'];kind=data['revision_source'];stamp=data['built_at']
        if data['version']!=__version__ or not re.fullmatch(r'[0-9a-f]{40}',revision) or type(verified) is not bool:raise ValueError()
        if kind not in ('git-head','user-provided-zip') or verified!=(kind=='git-head'):raise ValueError()
        if not re.fullmatch(r'[0-9a-f]{40}',identity) or verified and identity!=revision:raise ValueError()
        time=datetime.fromisoformat(stamp.replace('Z','+00:00'))
        if time.utcoffset() is None or time.utcoffset().total_seconds()!=0:raise ValueError()
        result.update(short_revision=revision[:7],built_at=stamp,revision_verified=verified,source_kind=kind,
                      fingerprint=hashlib.sha256((__version__+'|'+revision+'|'+identity+'|'+str(verified)).encode()).hexdigest())
        if admin:result.update(revision=revision,build_identity=identity)
    except (OSError,ValueError,KeyError,TypeError,AttributeError):pass
    try:result['changelog']=json.loads(NOTES.read_text(encoding='utf-8'))
    except (OSError,ValueError):result['changelog']=[]
    return result
