"""Saved-revision preview is read-only and cannot bypass publication or access control."""
from sqlalchemy import select,func
from test_content import client,make_type,write,update_payload
from test_blog import reader_client
from test_api import SessionLocal,reset_limiter
from app.content_models import RecordRevision


def test_exact_saved_revision_preview_does_not_publish_or_create_history(client):
    t=make_type(client)
    r=write(client,'/records',{'type_id':t['id'],'schema_version':1,'title':'虚构草稿','body':'# 预览正文','display_date':'2026-10-19','status':'draft','values':{}}).json()
    def count():
        with SessionLocal() as db:return db.scalar(select(func.count()).select_from(RecordRevision).where(RecordRevision.record_id==r['id']))
    before=count()
    url='/api/admin/blog/preview/'+r['id']
    preview=client.get(url,params={'expected_revision':r['revision']})
    assert preview.status_code==200
    assert preview.json()['preview_revision']==r['revision']
    assert preview.json()['body']=='# 预览正文'
    assert count()==before
    assert client.get('/api/blog/records/'+r['id']).status_code==404
    assert client.get('/api/admin/content/records/'+r['id']).json()==r
    updated=write(client,'/records/'+r['id'],update_payload(r,body='最新正文'),method='put').json()
    assert client.get(url,params={'expected_revision':r['revision']}).status_code==409
    assert client.get(url,params={'expected_revision':updated['revision']}).json()['body']=='最新正文'
    assert client.get(url).status_code==200  # Legacy callers remain compatible.
    assert count()==before+1
    assert client.get(url,params={'expected_revision':0}).status_code==422


def test_preview_rejects_reader_anonymous_and_deleted_records(client):
    t=make_type(client)
    r=write(client,'/records',{'type_id':t['id'],'schema_version':1,'title':'隔离预览','display_date':'2026-10-19','status':'draft','values':{}}).json()
    url='/api/admin/blog/preview/'+r['id']+'?expected_revision=1'
    reader=reader_client(client.app)
    assert reader.get(url).status_code==403
    reader.cookies.clear()
    assert reader.get(url).status_code==401
    assert write(client,'/records/'+r['id'],{'expected_revision':1},method='delete').status_code==200
    assert client.get(url).status_code==404
