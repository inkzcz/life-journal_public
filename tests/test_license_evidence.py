"""Synthetic legal-evidence fixtures: no Docker/network/runtime data needed."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import subprocess
from types import SimpleNamespace
import zipfile

import pytest
from scripts import license_evidence as review


def test_curated_inventory_has_verbatim_notices_and_explicit_known_gaps():
    root=Path(__file__).resolve().parents[1]
    document=json.loads((root/'third_party/notice-index.json').read_text())
    index={entry['path']:entry for entry in document['files']}
    assert len(index)==len(document['files'])
    for path, entry in index.items():
        assert path.startswith('third_party/licenses/') and review.safe_name(path)
        assert hashlib.sha256((root/path).read_bytes()).hexdigest()==entry['sha256']
        assert entry['origins']
    inventory=json.loads((root/'third_party/redistribution-inventory.json').read_text())
    assert inventory['publication_approved'] is False
    assert inventory['corresponding_source_complete'] is False
    missing=[]
    for package in inventory['packages']:
        for path in package.get('notice_files',[]):assert path in index
        if package['ecosystem'] in ('pypi','deb','npm') and not package.get('notice_files'):
            missing.append(package.get('package_path',package.get('name','')))
    assert set(missing)=={'node_modules/@napi-rs/lzma-linux-x64-gnu','node_modules/de-indent'}
    for module in inventory['go_modules']:
        if module['version']=='(devel)':assert module['name']=='caddy'
        else:
            assert module['notice_files']
            assert all(path in index for path in module['notice_files'])
    for crate in inventory['rust_source_review']['packages']:
        assert crate['notices'] and all(path in index for path in crate['notices'])


def test_windows_git_settings_preserve_original_notice_bytes(tmp_path):
    root=Path(__file__).resolve().parents[1]
    (tmp_path/'.gitattributes').write_bytes((root/'.gitattributes').read_bytes())
    path=tmp_path/'third_party/licenses/evidence/synthetic.txt';path.parent.mkdir(parents=True)
    content='Copyright Synthetic Author\r\n合成许可声明\r\n'.encode();path.write_bytes(content)
    def git(*args):
        return subprocess.check_output(['git','-C',str(tmp_path),*args],stderr=subprocess.DEVNULL)
    git('init','-q');git('-c','core.autocrlf=true','add','.')
    git('-c','user.name=Synthetic','-c','user.email=fixture@example.invalid','commit','-qm','synthetic legal fixture')
    assert git('show','HEAD:third_party/licenses/evidence/synthetic.txt')==content
    data=git('-c','core.autocrlf=true','-c','core.eol=crlf','archive','--format=zip','HEAD')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.read('third_party/licenses/evidence/synthetic.txt')==content


def tar_bytes(files, links=()):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode='w') as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name); info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        for name, target in links:
            info = tarfile.TarInfo(name); info.type = tarfile.SYMTYPE; info.linkname = target
            archive.addfile(info)
    return result.getvalue()


def test_image_reader_resolves_copyright_aliases_common_texts_and_whiteouts(tmp_path):
    first=tar_bytes({'var/lib/dpkg/status':b'Package: libsynthetic\nVersion: 1\nArchitecture: amd64\nStatus: install ok installed\n\n',
                     'usr/share/doc/source/copyright':b'Synthetic copyright\n',
                     'usr/share/doc/removed/copyright':b'Obsolete synthetic text\n',
                     'usr/share/common-licenses/GPL-2':b'Synthetic common license fixture\n'},
                    [('usr/share/doc/libsynthetic','source')])
    second=tar_bytes({'usr/share/doc/removed/.wh.copyright':b''})
    config=b'{"architecture":"amd64","os":"linux"}'
    manifest=json.dumps([{'Config':'config.json','RepoTags':['synthetic:one'],'Layers':['first.tar','second.tar']}]).encode()
    path=tmp_path/'business.tar';path.write_bytes(tar_bytes({'config.json':config,'manifest.json':manifest,'first.tar':first,'second.tar':second}))
    output=tmp_path/'notices';output.mkdir();notices=[]
    report=review.image_evidence(path,output,notices)
    assert report['image']['config_sha256']==hashlib.sha256(config).hexdigest()
    assert report['packages'][0]['copyright_evidence_path']=='image/usr/share/doc/source/copyright'
    assert (output/'image/usr/share/common-licenses/GPL-2').read_bytes()==b'Synthetic common license fixture\n'
    assert not (output/'image/usr/share/doc/removed/copyright').exists()
    assert len(notices)==2


def test_image_notices_use_final_layers_and_resolve_copyright_aliases(tmp_path):
    first = tar_bytes({'usr/share/doc/source/copyright': b'Synthetic public credit\n',
                       'usr/share/doc/removed/copyright': b'Obsolete\n'},
                      [('usr/share/doc/libalias', 'source')])
    second = tar_bytes({'usr/share/doc/removed/.wh.copyright': b'',
                        'var/lib/dpkg/status': b'Package: libalias\nStatus: install ok installed\nVersion: 1.0\nArchitecture: amd64\n',
                        'opt/venv/lib/python3.12/site-packages/synthetic-1.dist-info/METADATA': b'Name: synthetic\nVersion: 1\nLicense-Expression: MIT\n\n',
                        'opt/venv/lib/python3.12/site-packages/synthetic-1.dist-info/licenses/LICENSE': b'Verbatim synthetic notice\n'})
    archive = tmp_path/'business.tar'
    archive.write_bytes(tar_bytes({'manifest.json': json.dumps([{'Config': 'config.json', 'Layers': ['first.tar','second.tar'], 'RepoTags':['synthetic:1']}]).encode(),
                                  'config.json': b'{"architecture":"amd64","os":"linux"}',
                                  'first.tar': first, 'second.tar': second}))
    output = tmp_path/'new'; output.mkdir(); notices=[]
    result=review.image_evidence(archive,output,notices)
    package=next(x for x in result['packages'] if x['ecosystem']=='deb')
    assert package['copyright_evidence_path']=='image/usr/share/doc/source/copyright'
    assert not (output/'image/usr/share/doc/removed/copyright').exists()
    assert (output/'image/usr/share/doc/source/copyright').read_bytes()==b'Synthetic public credit\n'
    assert not any(p.suffix=='.so' for p in output.rglob('*'))


def go_string(data):
    size=len(data); prefix=bytearray()
    while size>=128:prefix.append((size&127)|128);size>>=7
    return bytes(prefix)+bytes([size])+data


def test_go_build_metadata_is_read_without_running_the_binary():
    modules=b'x'*16+b'mod\texample.invalid/synthetic\tv1.0.0\th1:synthetic\n'+b'y'*16
    header=b'\xff Go buildinf:'+bytes([8,2])+b'\0'*16
    version,rows=review.go_build_modules(b'ELF'+header+go_string(b'go1.synthetic')+go_string(modules))
    assert version=='go1.synthetic' and rows[0]['name']=='example.invalid/synthetic'
    with pytest.raises(ValueError):review.go_build_modules(b'not-Go')
    with pytest.raises(ValueError):review.go_build_modules(header+b'\x80'*10)


@pytest.mark.parametrize('name',['../outside','/absolute','folder/../outside','a\\b','a\nfile'])
def test_notice_paths_cannot_escape_output(tmp_path,name):
    with pytest.raises(ValueError):review.write_notice(tmp_path,name,b'Synthetic',[],'synthetic')


def test_existing_notices_are_preserved_and_still_registered(tmp_path):
    notices=[]
    review.write_notice(tmp_path,'LICENSE.txt',b'Synthetic\n',notices,'synthetic')
    second=[]
    review.write_notice(tmp_path,'LICENSE.txt',b'Synthetic\n',second,'synthetic')
    assert len(second)==1 and second[0]['sha256']==hashlib.sha256(b'Synthetic\n').hexdigest()
    with pytest.raises(ValueError):review.write_notice(tmp_path,'LICENSE.txt',b'changed',second,'synthetic')
    assert (tmp_path/'LICENSE.txt').read_bytes()==b'Synthetic\n'


def test_npm_download_checks_integrity_before_reading_notices(monkeypatch):
    data=tar_bytes({'package/LICENSE': b'Synthetic notice\n'})
    zipped=io.BytesIO()
    import gzip
    payload=gzip.compress(data)
    class Response(io.BytesIO):
        url='https://registry.npmjs.org/synthetic/-/synthetic-1.tgz'
    monkeypatch.setattr(review.urllib.request,'urlopen',lambda *a,**kw:Response(payload))
    package={'resolved':Response.url,'integrity':'sha512-'+base64.b64encode(hashlib.sha512(payload).digest()).decode()}
    assert review.npm_archive(package)==[('package/LICENSE',b'Synthetic notice\n')]
    package['integrity']='sha512-'+base64.b64encode(b'x'*64).decode()
    with pytest.raises(ValueError,match='integrity'):review.npm_archive(package)
    with pytest.raises(ValueError):review.npm_archive({'resolved':'https://user:synthetic@example.invalid/archive'})


def test_go_archives_match_binary_module_checksums(monkeypatch):
    prefix='example.invalid/synthetic@v1.0.0/'
    content=b'Synthetic license\n';buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive:archive.writestr(prefix+'LICENSE',content)
    line=hashlib.sha256(content).hexdigest()+'  '+prefix+'LICENSE\n'
    expected='h1:'+base64.b64encode(hashlib.sha256(line.encode()).digest()).decode()
    monkeypatch.setattr(review.urllib.request,'urlopen',lambda *a,**kw:io.BytesIO(buffer.getvalue()))
    module={'name':'example.invalid/synthetic','version':'v1.0.0','go_sum':expected}
    assert review.go_archive(module)
    module['go_sum']='h1:synthetic-mismatch'
    with pytest.raises(ValueError,match='checksum'):review.go_archive(module)
