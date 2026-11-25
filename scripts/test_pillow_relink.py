"""Host-side, local-only wrapper; only three known source/code files are mounted."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.command_errors import summarize
from scripts import local_images


def reviewed_relink_tag(tag):
    candidate=re.fullmatch(r'v5\.1\.(?:9|10|11)-candidate\.([0-9a-f]{7,40})',tag)
    if tag not in ('v5.1.9','v5.1.10','v5.1.11') and candidate is None:
        raise ValueError('Only reviewed v5.1.9/v5.1.10/v5.1.11 releases or source-bound candidates are accepted')
    return candidate


def validate_relink_image(tag,image):
    candidate=reviewed_relink_tag(tag)
    labels=(image or {}).get('Config',{}).get('Labels',{})
    revision=labels.get('org.opencontainers.image.revision','')
    if not re.fullmatch('[0-9a-f]{40}',revision) or candidate and not revision.startswith(candidate[1]):
        raise ValueError('Relink candidate tag does not match source revision')
    local_images.validate_image(image,revision,tag)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-tag',required=True)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('New report path required; nothing overwritten')
    try:reviewed_relink_tag(args.image_tag)
    except ValueError as error:parser.error(str(error))
    # Reuse the same remote-Docker rejection as the business delivery tools.
    commands=local_images.Docker()
    local_images.local_context(commands)
    validate_relink_image(args.image_tag,local_images.inspect(commands,'life-journal:'+args.image_tag))
    private=Path(os.environ['RUNNER_TEMP']).resolve()
    receipts=json.loads((args.sources/'sources.json').read_text())
    package=next(r for r in receipts['records'] if r.get('ecosystem')=='pypi' and r['name'].lower()=='pillow')
    record=package['files'][0];source=(args.sources/record['path']).absolute()
    probe=Path(__file__).resolve().parents[1]/'tests/pillow_relink_probe.py'
    redactor=Path(__file__).resolve().parent/'command_errors.py'
    if (source.is_symlink() or any(p.is_symlink() for p in source.parents)
            or private not in source.resolve().parents or not source.is_file()
            or hashlib.file_digest(source.open('rb'),'sha256').hexdigest()!=record['sha256']):
        parser.error('Only an exact, new runner-private source archive is accepted')
    name='lj-lgpl-pillow-'+secrets.token_hex(6)
    existing=subprocess.run(['docker','ps','-a','--filter','name=^/'+name+'$','--format','{{.ID}}'],
                            capture_output=True,text=True,check=True)
    if existing.stdout.strip():
        parser.error('Validation container name already exists; nothing changed')
    cmd=['docker','run','--rm','--pull=never','--platform','linux/amd64','--name',name,
         '--label','io.life-journal.pillow-drill='+name,
         '--mount','type=bind,src='+str(source)+',dst=/input/pillow.tar.gz,readonly',
         '--mount','type=bind,src='+str(probe)+',dst=/probe.py,readonly',
         '--mount','type=bind,src='+str(redactor)+',dst=/command_errors.py,readonly',
         '-e','RUN_LJ_PILLOW_RELINK=1','-e','LJ_PILLOW_SOURCE_SHA256='+record['sha256'],
         '--entrypoint','python','life-journal:'+args.image_tag,'/probe.py']
    try:
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=1200)
        if result.returncode:
            raise RuntimeError('Isolated LGPL relink failed; exit='+str(result.returncode)+'; '+summarize(result.stderr))
        report=json.loads(result.stdout.strip().splitlines()[-1])
        remaining=subprocess.run(['docker','ps','-a','--filter','name=^/'+name+'$','--format','{{.ID}}'],capture_output=True,text=True,check=True)
        if remaining.stdout.strip():
            raise RuntimeError('LGPL container cleanup incomplete')
    except BaseException:
        # Only this invocation's randomly named container is addressed. No prune,
        # images, volumes, Compose projects or host data directories are removed.
        owner=subprocess.run(['docker','inspect',name,'--format',
            '{{index .Config.Labels "io.life-journal.pillow-drill"}}'],capture_output=True,text=True)
        if owner.returncode==0 and owner.stdout.strip()==name:
            subprocess.run(['docker','stop','--time','10',name],capture_output=True,text=True)
        raise
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':
    main()
