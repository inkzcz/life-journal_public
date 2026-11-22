"""Source provenance/checksum boundaries; downloaded sources are never executed."""
import hashlib
import io
from pathlib import Path

import pytest

from scripts import corresponding_sources as sources


def descriptor(version='1.0-1',name='synthetic',filename='synthetic_1.0.orig.tar.gz'):
    return (f'Source: {name}\nVersion: {version}\nChecksums-Sha256:\n '+
            hashlib.sha256(b'Synthetic source archive').hexdigest()+' 24 '+filename+'\n').encode()


def test_exact_descriptor_handles_clearsign_and_rejects_wrong_source_version():
    raw=descriptor()
    signed=b'-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA256\n\n'+raw+b'-----BEGIN PGP SIGNATURE-----\nSynthetic\n'
    rows=sources.dsc_files(signed,'synthetic','1.0-1')
    assert rows[0]['name']=='synthetic_1.0.orig.tar.gz' and rows[0]['size']==24
    with pytest.raises(ValueError,match='version mismatch'):sources.dsc_files(raw,'synthetic','2')
    with pytest.raises(ValueError):sources.dsc_files(descriptor(filename='../escape'),'synthetic','1.0-1')


@pytest.mark.parametrize('url',[
    'http://snapshot.debian.org/source','https://user:synthetic'+'@'+'pypi.org/source',
    'https://127.0.0.1/private','https://nas.example.invalid/source',
    'https://pypi.org/source#private',
])
def test_source_transport_rejects_private_unapproved_or_credential_urls(url):
    with pytest.raises(ValueError):sources.checked_url(url)


def test_download_published_checksum_and_size_are_mandatory(tmp_path,monkeypatch):
    raw=b'Synthetic source archive'
    class Response(io.BytesIO):
        url='https://snapshot.debian.org/file/synthetic'
    monkeypatch.setattr(sources.urllib.request,'urlopen',lambda *a,**k:Response(raw))
    output=tmp_path/'source.tar.gz'
    with pytest.raises(ValueError,match='checksum required'):
        sources.save_download(Response.url,output)
    with pytest.raises(ValueError,match='mismatch'):
        sources.save_download(Response.url,output,sha256='0'*64)
    assert not output.exists() and output.with_name(output.name+'.partial').exists()
    second=tmp_path/'second.tar.gz'
    receipt=sources.save_download(Response.url,second,sha256=hashlib.sha256(raw).hexdigest(),size=len(raw))
    assert second.read_bytes()==raw and receipt['size']==len(raw)
    with pytest.raises(ValueError,match='nothing overwritten'):
        sources.save_download(Response.url,second,sha256=receipt['sha256'])


def test_binary_nmu_uses_source_version_not_binary_version():
    assert sources.source_identity({'name':'libsynthetic1','version':'1+b2','source_package':'synthetic (1)'})==('synthetic','1')
    with pytest.raises(ValueError):sources.source_identity({'name':'fixture','version':'1','source_package':'../outside'})


def test_browser_corresponding_source_uses_exact_publisher_commit(monkeypatch,tmp_path):
    revision='a'*40;calls=[]
    monkeypatch.setattr(sources,'json_fetch',lambda url:{'repository':{'url':'git+https://github.com/example/synthetic.git'},'gitHead':revision})
    def store(repo,commit,path):calls.append((repo,commit,path));return {'path':'synthetic-source'}
    monkeypatch.setattr(sources,'published_github_source',store)
    rows=sources.browser_sources({'packages':[{'name':'synthetic','version':'1'}]},tmp_path)
    assert calls==[('example/synthetic',revision,tmp_path)]
    assert rows[0]['ecosystem']=='browser-preferred-source'


def test_source_filename_cannot_escape_archive_directory():
    for filename in ('../escape','/absolute','a\\b','name\nsecret','..hidden'):
        with pytest.raises(ValueError):sources.file_name(filename)
