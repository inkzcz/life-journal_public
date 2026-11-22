"""Rebuild an interface-compatible modification of Pillow's LGPL FriBiDi shim.

Runs only in a disposable CI container with an integrity-checked upstream sdist
mounted read-only. Installs build headers in that container, never in the runtime
image. No database, deployment directory, Docker socket or media is mounted.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from command_errors import summarize


def command(*args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, timeout=600, **kwargs)
    if result.returncode:
        raise RuntimeError('Pillow relink step failed: '+args[0]+'; exit='+str(result.returncode)
                           +'; '+summarize(result.stderr or result.stdout))
    return result


def main():
    if (os.environ.get('RUN_LJ_PILLOW_RELINK') != '1' or os.getuid() != 0
            or not Path('/input/pillow.tar.gz').is_file()):
        raise RuntimeError('Explicit disposable source-only relink container required')
    source = Path('/input/pillow.tar.gz')
    expected = os.environ.get('LJ_PILLOW_SOURCE_SHA256', '')
    if hashlib.file_digest(source.open('rb'), 'sha256').hexdigest() != expected:
        raise RuntimeError('Pillow source integrity mismatch')
    work = Path('/tmp/pillow-relink'); work.mkdir()
    with tarfile.open(source) as archive:
        if sum(m.size for m in archive.getmembers()) > 512 * 1024 * 1024:
            raise RuntimeError('Unexpected source expansion')
        archive.extractall(work, filter='data')
    roots = list(work.glob('pillow-*'))
    if len(roots) != 1:
        raise RuntimeError('Unexpected Pillow source layout')
    root = roots[0]
    shim = root/'src/thirdparty/fribidi-shim/fribidi.c'
    text = shim.read_text()
    marker = 'LJ_LGPL_SHIM_REBUILT'
    signature = 'int load_fribidi(void) {'
    if text.count(signature) != 1:
        raise RuntimeError('Reviewed LGPL shim function was not found')
    shim.write_text('#include <stdio.h>\n'+text.replace(signature,
        signature+'\n    fprintf(stderr, "'+marker+'\\n");'))
    command('apt-get','update')
    command('apt-get','install','-y','--no-install-recommends','gcc','libc6-dev','libfreetype-dev',
            'libharfbuzz-dev','libjpeg-dev','zlib1g-dev')
    command(sys.executable,'-m','pip','wheel','--no-deps','--no-cache-dir',
            '--wheel-dir','/tmp/relinked-wheel','--config-settings=raqm=enable',
            '--config-settings=raqm=vendor','--config-settings=fribidi=vendor',str(root))
    wheels = list(Path('/tmp/relinked-wheel').glob('pillow-*.whl'))
    if len(wheels) != 1:
        raise RuntimeError('Expected exactly one rebuilt library wheel')
    command(sys.executable,'-m','pip','install','--no-deps','--no-index','--target',
            '/tmp/relinked-library',str(wheels[0]))
    probe = '''
import io,os,json
from pathlib import Path
from PIL import Image, ImageFont, _imagingft
assert os.getuid()==os.getgid()==10001
assert Path('/tmp/relinked-library') in Path(Image.__file__).parents
font=ImageFont.load_default()
assert font.getbbox('Compatible modified library')
data=io.BytesIO();Image.new('RGB',(8,8),'blue').save(data,format='JPEG')
with Image.open(io.BytesIO(data.getvalue())) as image:assert image.size==(8,8)
print(json.dumps({'modified_lgpl_shim_loaded':True,'library_relinked_from_source':True,
                  'pillow_api_compatible':True,'jpeg_round_trip':True,'uid':os.getuid()}))
'''
    result = command(sys.executable,'-c',probe, env=dict(os.environ,
        PYTHONPATH='/tmp/relinked-library',PYTHONDONTWRITEBYTECODE='1'),
        cwd='/tmp',user=10001,group=10001)
    if marker not in result.stderr:
        raise RuntimeError('Modified LGPL shim did not execute')
    print(json.dumps(json.loads(result.stdout),sort_keys=True))


if __name__ == '__main__':
    main()
