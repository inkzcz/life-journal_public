"""Phase3M immutable private derivatives; only synthetic images/temporary storage."""
import io,hashlib
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from test_archive import client,upload
from test_api import login,csrf,SessionLocal
from app.archive_models import MediaAsset


def large_image():
    stream=io.BytesIO();image=Image.effect_noise((2400,1600),70).convert('RGB')
    exif=Image.Exif();exif[274]=6;exif[270]='synthetic private metadata'
    image.save(stream,'JPEG',quality=90,exif=exif);return stream.getvalue()


def test_small_derivative_orientation_integrity_permissions_and_legacy_fallback(client):
    raw=large_image();asset=upload(client,raw).json();id=asset['id']
    assert (asset['width'],asset['height'])==(2400,1600)
    assert (asset['preview_width'],asset['preview_height'])==(1067,1600)
    small=client.get('/api/library-media/'+id+'/thumbnail');large=client.get('/api/library-media/'+id+'/preview')
    assert small.status_code==large.status_code==200
    assert len(small.content)<len(large.content)<len(raw)
    assert hashlib.sha256(small.content).hexdigest()==asset['thumbnail_sha256']
    for response,edge in [(small,640),(large,1600)]:
        assert response.headers['cache-control']=='no-store' and response.headers['x-content-type-options']=='nosniff'
        with Image.open(io.BytesIO(response.content)) as decoded:
            assert max(decoded.size)==edge and decoded.height>decoded.width and not decoded.getexif() and 'xmp' not in decoded.info
    assert client.get('/api/library-media/'+id+'/original').content==raw
    with TestClient(client.app,base_url='https://testserver') as anonymous:
        assert anonymous.get('/api/library-media/'+id+'/thumbnail').status_code==401
    # Released uploads have no small derivative. GET reads preview; never mutates storage.
    folder=client.app.state.settings.media_dir/'library-v1'/id
    with SessionLocal() as db:
        db.get(MediaAsset,id).thumbnail_sha256=None;db.commit()
    (folder/'thumbnail.webp').unlink()
    before={p.name:p.read_bytes() for p in folder.iterdir()}
    assert client.get('/api/library-media/'+id+'/thumbnail').content==large.content
    assert {p.name:p.read_bytes() for p in folder.iterdir()}==before


def test_legacy_preview_keeps_original_and_fallback_read_is_nonmutating(client):
    # Explicit archival fixture; no legacy router in production.
    from legacy_backend import journals,media
    client.app.include_router(journals.router);client.app.include_router(media.router)
    headers=csrf(client);journal=client.post('/api/journals',headers=headers,json={'title':'合成旧日记'}).json()
    raw=large_image();mid=client.post('/api/journals/'+str(journal['id'])+'/media',headers=headers,files={'file':('synthetic.jpg',raw)}).json()['id']
    folder=client.app.state.settings.media_dir;derived=folder/'legacy-previews-v1'/(mid+'.webp')
    preview=client.get('/api/media/'+mid+'/preview');assert preview.status_code==200 and len(preview.content)<len(raw)
    assert client.get('/api/media/'+mid).content==raw
    with Image.open(io.BytesIO(preview.content)) as image:assert max(image.size)==640 and not image.getexif()
    with TestClient(client.app,base_url='https://testserver') as anonymous:assert anonymous.get('/api/media/'+mid+'/preview').status_code==401
    derived.unlink();assert client.get('/api/media/'+mid+'/preview').content==preview.content and not derived.exists()
    assert client.delete('/api/journals/'+str(journal['id']),headers=headers).status_code==200
    assert not (folder/mid).exists() and not derived.exists()


def test_partial_legacy_derivative_write_cleans_both_files(client,monkeypatch):
    # Explicit archival fixture; no legacy router in production.
    from legacy_backend import journals,media
    client.app.include_router(journals.router);client.app.include_router(media.router)
    import pytest
    from sqlalchemy import select,func
    from app.models import Media
    headers=csrf(client);j=client.post('/api/journals',headers=headers,json={'title':'合成失败上传'}).json()
    folder=client.app.state.settings.media_dir
    before={str(p) for p in folder.rglob('*') if p.is_file()}
    original=Path.write_bytes
    def fail(path,data):
        if path.parent.name=='legacy-previews-v1':
            original(path,b'partial synthetic preview');raise OSError('synthetic storage failure')
        return original(path,data)
    with monkeypatch.context() as patch:
        patch.setattr(Path,'write_bytes',fail)
        with pytest.raises(OSError,match='synthetic storage failure'):
            client.post('/api/journals/'+str(j['id'])+'/media',headers=headers,files={'file':('synthetic.png',large_image())})
    assert {str(p) for p in folder.rglob('*') if p.is_file()}==before
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Media).where(Media.journal_id==j['id']))==0
