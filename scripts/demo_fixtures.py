"""Locally generate deterministic synthetic exchange fixtures; no external data."""
import io
import json
from pathlib import Path
import zipfile


def package_bytes(document):
    from PIL import Image
    files={'manifest.json':json.dumps({'format':'life-journal.package','version':1,
                                      'documents':['travel.json']}).encode(),
           'travel.json':json.dumps(document,ensure_ascii=False).encode()}
    for name,color in (('plate-a','#659ca1'),('plate-b','#d7a67a')):
        stream=io.BytesIO()
        Image.new('RGB',(96,72),color).save(stream,format='JPEG',quality=85)
        files['photos/'+name+'.jpg']=stream.getvalue()
    result=io.BytesIO()
    with zipfile.ZipFile(result,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):
            entry=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o100644<<16
            archive.writestr(entry,data)
    return result.getvalue()


def example_bytes(root):
    """Read the synthetic example and generate its package entirely in memory."""
    path=Path(root)/'docs/v5.1.5/examples/travel.json'
    return package_bytes(json.loads(path.read_text()))


def prepare(root):
    root=Path(root)/'docs/v5.1.5/examples'
    data=package_bytes(json.loads((root/'travel.json').read_text()))
    target=root/'travel-with-photos.zip'
    if target.exists():
        if target.read_bytes()!=data:raise RuntimeError('Different fixture already exists; retained for owner inspection')
        return target
    with target.open('xb') as output:output.write(data)
    return target
