"""Synthetic images and isolated databases only. No NAS or real files."""
import io
import uuid
import hashlib
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from test_content import client, make_type, record_payload, update_payload, write, type_payload
from test_api import app, login, csrf, reset_limiter, SessionLocal, engine
from app.archive_models import MediaAsset,RecordMedia,RecordLink,Place,RecordPlace
from app.content_models import ContentRecord,RecordRevision
A='/api/admin/archive'
C='/api/admin/content'

def image_bytes(fmt='JPEG',exif=False):
    out=io.BytesIO();im=Image.new('RGB',(24,16),'#86a48e')
    meta=Image.Exif();meta[270]='synthetic private metadata';meta[274]=6
    im.save(out,format=fmt,**({'exif':meta} if exif else {}));return out.getvalue()

def upload(c,data=None,name='synthetic.jpg'):
    return c.post(A+'/media',headers=csrf(c),files={'file':(name,data if data is not None else image_bytes(),'text/html')})

def create_record(c,t,**kw):
    payload=record_payload(t);payload.update(kw)
    r=write(c,'/records',payload);assert r.status_code==200,r.text;return r.json()

def connect(c,r,media=None,links=None,places=None):
    return write(c,'/records/'+r['id'],update_payload(r,connections={'media':media or [],'links':links or [],'places':places or []}),'put')

def test_media_upload_privacy_metadata_and_validation(client):
    data=image_bytes(exif=True);response=upload(client,data,'../../synthetic.jpg');assert response.status_code==200,response.text
    m=response.json();id=m['id'];assert m['filename']=='synthetic.jpg' and m['mime_type']=='image/jpeg'
    assert m['sha256']==hashlib.sha256(data).hexdigest() and (m['width'],m['height'])==(24,16)
    assert not {'path','storage_path','storage_key'}&m.keys()
    preview=client.get('/api/library-media/'+id+'/preview');assert preview.status_code==200
    assert preview.headers['cache-control']=='no-store'
    with Image.open(io.BytesIO(preview.content)) as image:
        assert not image.getexif() and image.size==(16,24) and 'xmp' not in image.info
    original=client.get('/api/library-media/'+id+'/original');assert original.content==data and 'attachment' in original.headers['content-disposition']
    assert client.get('/api/library-media/'+id+'/invalid').status_code==404
    for fmt in ['PNG','WEBP']:
        assert upload(client,image_bytes(fmt),'fake.svg').status_code==200
    for bad in [b'<svg onload="alert(1)"></svg>',b'<html>bad</html>',b'not an image',data[:80]]:
        assert upload(client,bad).status_code==415
    assert upload(client,b'x'*(10*1024*1024+1)).status_code==413
    updated=client.put(A+'/media/'+id,headers=csrf(client),json={'expected_revision':1,'title':'虚构图片','description':'说明','alt':'替代文本'})
    assert updated.status_code==200 and updated.json()['revision']==2
    assert client.put(A+'/media/'+id,headers=csrf(client),json={'expected_revision':1,'title':'冲突'}).status_code==409
    assert client.get(A+'/media?q=虚构图片').json()['total']==1
    with TestClient(client.app,base_url='https://testserver') as fresh:
        login(fresh);assert fresh.get('/api/library-media/'+id+'/preview').content==preview.content
    with TestClient(client.app,base_url='https://testserver') as anonymous:
        assert anonymous.get('/api/library-media/'+id+'/preview').status_code==401
        assert anonymous.get('/api/library-media/'+id+'/original').status_code==401


def test_media_reuse_order_cover_delete_and_history(client):
    m=upload(client).json();m2=upload(client,image_bytes('PNG')).json();t=make_type(client)
    first=create_record(client,t);second=create_record(client,t)
    refs=[{'id':m['id'],'cover':True,'caption':'封面备注'},{'id':m2['id']}]
    res=connect(client,first,refs);assert res.status_code==200,res.text;first=res.json()
    second=connect(client,second,[{'id':m['id']}]).json()
    assert len(client.get(A+'/media/'+m['id']).json()['references'])==2
    assert client.request('DELETE',A+'/media/'+m['id'],headers=csrf(client),json={'expected_revision':1}).status_code==409
    assert [x['id'] for x in first['connections']['media']]==[m['id'],m2['id']]
    first=connect(client,first,[{'id':m2['id'],'cover':True},{'id':m['id'],'caption':'新的备注'}]).json()
    assert first['connections']['media'][0]['cover']
    first=connect(client,first,[{'id':m2['id']}]).json()
    assert client.get('/api/library-media/'+m['id']+'/preview').status_code==200
    assert client.get(C+'/records/'+second['id']).json()['connections']['media'][0]['id']==m['id']
    assert write(client,'/records/'+second['id'],{'expected_revision':second['revision']},'delete').status_code==200
    assert client.get('/api/library-media/'+m['id']+'/original').status_code==200
    assert client.get(A+'/media/'+m['id']).json()['references'][0]['deleted']
    assert client.request('DELETE',A+'/media/'+m['id'],headers=csrf(client),json={'expected_revision':1}).status_code==409
    unused=upload(client).json()
    assert client.request('DELETE',A+'/media/'+unused['id'],headers=csrf(client),json={'expected_revision':1}).status_code==200
    assert client.get('/api/library-media/'+unused['id']+'/preview').status_code==404
    folder=client.app.state.settings.media_dir/'library-v1'/unused['id']
    assert (folder/'original').is_file() and (folder/'preview.webp').is_file()
    with SessionLocal() as db:
        snapshots=list(db.scalars(select(RecordRevision).where(RecordRevision.record_id==first['id'])))
        assert any(len(s.snapshot['connections']['media'])==2 for s in snapshots)


def test_record_links_direction_cycle_duplicates_deleted_and_place_sharing(client):
    t=make_type(client);a=create_record(client,t);b=create_record(client,t)
    p=client.post(A+'/places',headers=csrf(client),json={'name':'虚构花园','city':'虚构城','category':'自选类别','latitude':'31.230400','longitude':'121.473700'}).json()
    a=connect(client,a,links=[{'id':b['id'],'label':'专题包含'}],places=[p['id']]).json()
    b=client.get(C+'/records/'+b['id']).json();assert b['connections']['incoming'][0]['id']==a['id']
    b=connect(client,b,links=[{'id':a['id'],'label':'相关文章'}],places=[p['id']]).json() # Cycles are allowed.
    assert len(client.get(A+'/places/'+p['id']).json()['references'])==2
    for links in [[{'id':a['id'],'label':'自关联'}],[{'id':str(uuid.uuid4()),'label':'缺失'}],[{'id':b['id'],'label':'重复'}]*2]:
        assert connect(client,a,links=links).status_code==422
    assert connect(client,a,media=[{'id':str(uuid.uuid4())}]).status_code==404
    assert connect(client,a,media=[{'id':upload(client).json()['id'],'cover':True},{'id':upload(client).json()['id'],'cover':True}]).status_code==422
    assert write(client,'/records/'+b['id'],{'expected_revision':b['revision']},'delete').status_code==200
    a=client.get(C+'/records/'+a['id']).json();assert a['connections']['links'][0]['deleted']
    # Existing history may be retained; creating a new reference to deleted records is forbidden.
    retained=connect(client,a,links=[{'id':b['id'],'label':'专题包含'}]);assert retained.status_code==200,retained.text
    fresh=create_record(client,t)
    assert connect(client,fresh,links=[{'id':b['id'],'label':'新关联'}]).status_code==422
    a=retained.json();a=connect(client,a).json();assert not a['connections']['links']
    assert client.get(A+'/places?q=虚构城').json()['total']>=1
    edited=client.put(A+'/places/'+p['id'],headers=csrf(client),json={'expected_revision':1,'name':'更新地点','active':False});assert edited.status_code==200
    assert client.put(A+'/places/'+p['id'],headers=csrf(client),json={'expected_revision':1,'name':'冲突'}).status_code==409
    assert connect(client,fresh,places=[p['id']]).status_code==422
    for coordinates in [{'latitude':91,'longitude':0},{'latitude':0,'longitude':181},{'latitude':'NaN','longitude':0},{'latitude':1},{'latitude':'1.1234567','longitude':2}]:
        assert client.post(A+'/places',headers=csrf(client),json={'name':'无效',**coordinates}).status_code==422


def test_new_permissions_and_switch(client):
    from app.models import User
    from app.security import ph
    name='reader-'+uuid.uuid4().hex;password=uuid.uuid4().hex
    with SessionLocal() as db:db.add(User(username=name,password_hash=ph.hash(password)));db.commit()
    m=upload(client).json()
    with TestClient(client.app,base_url='https://testserver') as reader:
        reader.post('/api/auth/login',headers=csrf(reader),json={'username':name,'password':password})
        for path in ['/media','/places']:
            assert reader.get(A+path).status_code==403
            assert reader.post(A+path,headers=csrf(reader),json={}).status_code==403
        assert reader.get('/api/library-media/'+m['id']+'/preview').status_code==200
        assert reader.get('/api/library-media/'+m['id']+'/thumbnail').status_code==200
        assert reader.get('/api/library-media/'+m['id']+'/original').status_code==403
    with TestClient(app,base_url='https://testserver') as disabled:
        login(disabled)
        for path in ['/media','/places']:assert disabled.get(A+path).status_code==200
        assert disabled.get('/api/library-media/'+m['id']+'/preview').status_code==200
        assert disabled.get('/api/library-media/'+m['id']+'/thumbnail').status_code==200
        assert disabled.get('/api/journals').status_code==200
    assert client.post(A+'/places',json={'name':'csrf'}).status_code==403
    assert client.post(A+'/media',files={'file':('x.jpg',image_bytes())}).status_code==403


def test_media_delete_vs_attach_postgresql(client):
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL concurrency')
    t=make_type(client);r=create_record(client,t);m=upload(client).json();enabled=client.app
    def action(mode):
        with TestClient(enabled,base_url='https://testserver') as c:
            login(c)
            if mode=='attach':return connect(c,r,media=[{'id':m['id']}]).status_code
            return c.request('DELETE',A+'/media/'+m['id'],headers=csrf(c),json={'expected_revision':1}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(action,['attach','delete']))
    assert results in [[200,409],[404,200]],results
    with SessionLocal() as db:
        asset=db.get(MediaAsset,m['id']);count=db.scalar(select(func.count()).select_from(RecordMedia).where(RecordMedia.media_id==m['id']))
        assert not (asset.deleted_at and count)


def test_source_revision_and_link_vs_record_delete_postgresql(client):
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL concurrency')
    t=make_type(client);a=create_record(client,t);b=create_record(client,t);enabled=client.app
    def action(mode):
        with TestClient(enabled,base_url='https://testserver') as c:
            login(c)
            if mode=='attach':return connect(c,a,links=[{'id':b['id'],'label':'关联'}]).status_code
            return write(c,'/records/'+b['id'],{'expected_revision':b['revision']},'delete').status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(action,['attach','delete']))
    assert results in [[200,200],[422,200]],results
    current=client.get(C+'/records/'+a['id']).json()
    if current['connections']['links']:assert current['connections']['links'][0]['deleted']
    assert connect(client,a).status_code==(409 if current['revision']!=a['revision'] else 200)


def test_upload_failure_cleanup_pixel_bomb_and_animation(client,monkeypatch):
    from sqlalchemy.orm import Session
    folder=client.app.state.settings.media_dir/'library-v1'
    before=set(folder.iterdir()) if folder.exists() else set()
    original_commit=Session.commit
    def failing(db):
        if any(isinstance(x,MediaAsset) for x in db.new):raise RuntimeError('synthetic transaction failure')
        return original_commit(db)
    with monkeypatch.context() as scoped:
        scoped.setattr(Session,'commit',failing)
        with pytest.raises(RuntimeError,match='synthetic transaction failure'):upload(client)
    assert (set(folder.iterdir()) if folder.exists() else set())==before
    with monkeypatch.context() as scoped:
        scoped.setattr(Image,'MAX_IMAGE_PIXELS',10)
        assert upload(client).status_code==415
    data=io.BytesIO();frames=[Image.new('RGB',(10,10),color) for color in ['red','blue']]
    frames[0].save(data,format='PNG',save_all=True,append_images=frames[1:])
    assert upload(client,data.getvalue()).status_code==415


def test_legacy_record_update_keeps_connections_and_invalid_write_rolls_back(client):
    t=make_type(client);r=create_record(client,t,title='literal % _ \\ record');m=upload(client).json()
    r=connect(client,r,media=[{'id':m['id'],'caption':'保留引用'}]).json()
    assert client.get(C+'/records',params={'q':'% _ \\'}).json()['total']==1
    updated=write(client,'/records/'+r['id'],update_payload(r,title='旧客户端修改'),'put');assert updated.status_code==200
    r=updated.json();assert r['connections']['media'][0]['id']==m['id']
    failed=write(client,'/records/'+r['id'],update_payload(r,title='不应提交',connections={'media':[],'links':[{'id':str(uuid.uuid4()),'label':'缺失'}],'places':[]}),'put')
    assert failed.status_code==422
    after=client.get(C+'/records/'+r['id']).json()
    assert after['title']==r['title'] and after['revision']==r['revision'] and after['connections']['media']==r['connections']['media']


def test_concurrent_connection_updates_postgresql(client):
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL concurrency')
    t=make_type(client);r=create_record(client,t);images=[upload(client).json()['id'] for _ in range(2)];enabled=client.app
    def action(id):
        with TestClient(enabled,base_url='https://testserver') as c:
            login(c);return connect(c,r,media=[{'id':id,'cover':True}]).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(action,images))==[200,409]
    after=client.get(C+'/records/'+r['id']).json();assert after['revision']==2 and len(after['connections']['media'])==1


def test_database_cover_and_relationship_constraints_postgresql(client):
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL constraints')
    from sqlalchemy.exc import IntegrityError
    t=make_type(client);r=create_record(client,t);a,b=[upload(client).json()['id'] for _ in range(2)]
    with SessionLocal() as db:
        db.add(RecordMedia(record_id=r['id'],media_id=a,position=0,cover=True));db.commit()
        db.add(RecordMedia(record_id=r['id'],media_id=b,position=1,cover=True))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()
        db.add(RecordLink(source_id=r['id'],target_id=r['id'],label='自关联'))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()
        db.add(RecordPlace(record_id=r['id'],place_id=str(uuid.uuid4())))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()
