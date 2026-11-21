"""Untrusted transport and canonical syntax; no DB writes or real user data."""
import io,json,stat,zipfile
from uuid import uuid4
import pytest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from test_api import reset_limiter,engine  # Reuse the isolated suite database environment.
from app.exchange.parsers import parse,package,yaml_data,safe_path
from app.exchange.schemas import Exchange
from app.exchange.syntax import place_mark,media_mark,registry,KINDS
from app.services.markdown_marks import parse as marks
from app.services.body_media import blocks


def doc(**extra):
    return {'format':'life-journal.exchange','version':1,'records':[{'key':'story','type_slug':'custom-type','title':'合成文章','display_date':'2026-11-05','body':'普通正文'}],**extra}

def archive(files):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    return b.getvalue()

@pytest.mark.parametrize('kind',list(KINDS))
@pytest.mark.parametrize('name',['成都 餐厅','花*间*_[茶]','青瓷 <咖啡>','山\\海 `小馆`'])
def test_all_marks_roundtrip_existing_parser(kind,name):
    pid=str(uuid4());text=place_mark(kind,name,pid);m=marks(text).marks
    assert [(x['kind'],x['name'],x['place_id']) for x in m]==[(kind,name,pid)]
    assert not marks('```md\n'+text+'\n```').marks
    assert not marks('`'+place_mark(kind,'普通名称')+'`').marks

@pytest.mark.parametrize('name',['','\n名字','店\n名','名称@f 其他','名称 {#place:x}'])
def test_ambiguous_generated_names_rejected(name):
    with pytest.raises(ValueError):place_mark('f',name)


def test_media_roundtrip_and_old_defaults():
    value={'id':str(uuid4()),'alt':'中文','width':960,'align':'center','layout':'grid'}
    assert blocks(media_mark(value),2)==[value]
    assert blocks(media_mark({'id':value['id']}),2)==[{'id':value['id']}]
    with pytest.raises(ValueError):media_mark(value|{'width':True})
    with pytest.raises(ValueError):media_mark(value|{'html':'<script>'})
    assert {r['id'] for r in registry()['place_marks']}=={'@'+k for k in KINDS}


def test_json_markdown_equivalent_and_dates_separate():
    raw=doc();raw['records'][0].update(travel={'start_date':'2026-10-01','end_date':'2026-10-03'},tags=['旅行'])
    md='---\nformat: life-journal.exchange\nversion: 1\nrecord:\n  key: story\n  type_slug: custom-type\n  title: 合成文章\n  display_date: 2026-11-05\n  tags: [旅行]\n  travel:\n    start_date: 2026-10-01\n    end_date: 2026-10-03\n---\n普通正文'
    assert parse(json.dumps(raw).encode(),'content.json')==parse(md.encode(),'content.md')
    assert parse(md.encode(),'content.md').records[0].display_date.isoformat()=='2026-11-05'

@pytest.mark.parametrize('text',['a: &x [1]\nb: *x','a: 1\na: 2','!!python/object/apply:os.system [echo]','a: [' ])
def test_unsafe_yaml_is_rejected(text):
    with pytest.raises((ValueError,__import__('yaml').YAMLError)):yaml_data(text)

@pytest.mark.parametrize('path',['../x','/tmp/x','C:/x','a\\b','a/./b','a//b','a/../b','e\u0301.png'])
def test_archive_path_safety(path):
    with pytest.raises(ValueError):safe_path(path)


def test_zip_multi_document_explicit_shared_media_and_links():
    a=doc(media=[{'key':'plate','path':'photos/a.png'}]);a['records'][0]['media_keys']=['plate'];a['records'][0]['links']=[{'record_key':'second','label':'相关'}]
    b=doc();b['records'][0].update(key='second',media_keys=['plate'])
    files={'manifest.json':json.dumps({'format':'life-journal.package','version':1,'documents':['a.json','b.json']}),'a.json':json.dumps(a),'b.json':json.dumps(b),'photos/a.png':b'image bytes validated by image service later'}
    value,photos=package(archive(files));assert len(value.records)==2 and len(value.media)==1 and photos['photos/a.png']==files['photos/a.png']
    files['run.py']='print(1)'
    with pytest.raises(ValueError,match='未声明'):package(archive(files))


def test_zip_links_duplicates_compression_and_json_duplicates():
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:
        info=zipfile.ZipInfo('photo');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'/etc/passwd')
    with pytest.raises(ValueError):package(buf.getvalue())
    with pytest.raises(ValueError):package(archive({'manifest.json':'{}','Photo.jpg':'x','photo.jpg':'x'}))
    with pytest.raises(ValueError):package(archive({'bomb':'0'*100000}))
    with pytest.raises(ValueError):parse(b'{"version":1,"version":1}','x.json')

@pytest.mark.parametrize('version',[2,True,'1',1.0])
def test_unknown_or_coerced_format_versions_rejected(version):
    with pytest.raises(ValueError):Exchange.model_validate(doc(version=version))


def test_missing_dates_not_invented_and_foreign_refs_rejected():
    raw=doc();raw['records'][0].pop('display_date');assert Exchange.model_validate(raw).records[0].display_date is None
    raw['records'][0]['cover_key']='invented'
    with pytest.raises(ValueError):Exchange.model_validate(raw)


def test_registry_dispatch_and_text_barriers():
    from app.exchange.syntax import serialize
    for kind in KINDS:
        assert serialize('@'+kind,{'name':'中文名称'})==place_mark(kind,'中文名称')
    assert not marks('name@example.com https://example.com/@f/path').marks
    assert not marks('```\n@f 店\n```\n\n`@l 成都`').marks
    assert [x['kind'] for x in marks(place_mark('l','成都')+'\n'+place_mark('f','小馆')).marks]==['l','f']
    with pytest.raises(ValueError):serialize('@unknown',{'name':'名字'})
    with pytest.raises(ValueError):serialize('@f',{'name':'名字','sql':'DROP TABLE'})


def test_front_matter_cannot_silently_default_or_replace_body():
    with pytest.raises(ValueError):parse(b'{"records": []}','x.json')
    with pytest.raises(ValueError):parse(b'---\nrecord:\n  body: replaced\n---\noriginal','x.md')
    assert yaml_data('day: 2026-11-05')['day']=='2026-11-05'
    with pytest.raises(ValueError):yaml_data('a: '+('['*40)+'0'+(']'*40))


def test_checked_in_schema_and_real_examples_match_parser():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]/'docs/v5.1.5'
    assert json.loads((root/'content-exchange.schema.json').read_text())==Exchange.model_json_schema()
    assert len(parse((root/'examples/article.md').read_bytes(),'article.md').records)==1
    assert len(parse((root/'examples/travel.json').read_bytes(),'travel.json').records[0].foods)==2
    from scripts.demo_fixtures import example_bytes
    value,photos=package(example_bytes(root.parents[1]))
    from PIL import Image
    assert len(photos)==2
    for data in photos.values():
        with Image.open(io.BytesIO(data)) as image:assert image.format=='JPEG';image.verify()
