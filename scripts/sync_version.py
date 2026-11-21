"""VERSION is canonical; synchronize/check mirrors required by separate image contexts."""
import argparse,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PATTERN=re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?')

def product_version(root=ROOT):
    version=(root/'VERSION').read_text(encoding='utf-8').strip()
    if not PATTERN.fullmatch(version):raise ValueError('VERSION must contain a product version without v prefix')
    return version

def mirrors(root=ROOT):
    version=product_version(root);result={}
    for name,pattern in [('backend/app/version.py',r"__version__='[^']+'"),('frontend/src/version.ts',r"VERSION='[^']+'"),('scripts/release_local.py',r"TOOL_VERSION='[^']+'")]:
        text=(root/name).read_text(encoding='utf-8');prefix={'backend/app/version.py':'__version__','frontend/src/version.ts':'VERSION','scripts/release_local.py':'TOOL_VERSION'}[name]
        updated,count=re.subn(pattern,prefix+"='"+version+"'",text)
        if count!=1:raise ValueError('Unrecognized version mirror: '+name)
        result[name]=updated
    for name in ['frontend/package.json','frontend/package-lock.json']:
        data=json.loads((root/name).read_text(encoding='utf-8'));data['version']=version
        if name.endswith('package-lock.json'):data['packages']['']['version']=version
        result[name]=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    return result

def check(root=ROOT):
    drift=[name for name,text in mirrors(root).items() if (root/name).read_text(encoding='utf-8')!=text]
    if drift:raise ValueError('Version mirrors differ from VERSION: '+', '.join(drift)+'; run python scripts/sync_version.py')
    return product_version(root)

def build_tag(tag,root=ROOT):
    version=product_version(root)
    if re.fullmatch('[0-9a-f]{40}',tag) or re.fullmatch('v'+re.escape(version)+r'(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?',tag):return
    raise ValueError('Image tag must match VERSION (v'+version+'), a prerelease suffix, or a CI commit SHA')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');args=p.parse_args()
    if not args.check:
        for name,text in mirrors().items():(ROOT/name).write_text(text,encoding='utf-8',newline='\n')
    print('Product version mirrors verified: '+check())
if __name__=='__main__':main()
