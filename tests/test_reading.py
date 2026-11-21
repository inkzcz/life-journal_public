"""Read-only keyset neighbors reuse the reader visibility and list total order."""
import uuid
from sqlalchemy import select,func,event
from test_content import client,make_type,write,type_payload
from test_archive import create_record,upload,connect
from test_blog import reader_client,section
from test_api import SessionLocal,engine
from app.content_models import RecordRevision,ContentRecord

BASE='/api/blog/records'
def all_records(c):
    items=[];page=1
    while True:
        data=c.get(BASE,params={'page':page}).json();items.extend(data['items'])
        if len(items)>=data['total']:return items
        page+=1

def test_neighbors_follow_global_order_across_pages_and_same_dates_without_writes(client):
    t=make_type(client)
    created=[create_record(client,t,title='合成同日 '+str(i),display_date='8999-10-20') for i in range(15)]
    draft=create_record(client,t,status='draft',display_date='8999-10-20',title='不能泄露的草稿')
    deleted=create_record(client,t,display_date='8999-10-20',title='不能泄露的回收记录')
    assert write(client,'/records/'+deleted['id'],{'expected_revision':deleted['revision']},'delete').status_code==200
    hidden_type=make_type(client);hidden=create_record(client,hidden_type,display_date='8999-10-20',title='不能泄露的停用类型')
    assert write(client,'/types/'+hidden_type['id'],type_payload(hidden_type,active=False),'put').status_code==200
    # Section membership does not secretly change the explicitly global context.
    section(client,[t]);media=upload(client).json();with_cover=connect(client,created[0],media=[{'id':media['id'],'cover':True}]).json()
    reader=reader_client(client.app);ordered=all_records(reader);ids=[x['id'] for x in ordered]
    own=[id for id in ids if id in {r['id'] for r in created}];assert own==sorted(own)
    assert not {draft['id'],deleted['id'],hidden['id']} & set(ids)
    with SessionLocal() as db:before=db.scalar(select(func.count()).select_from(RecordRevision));snapshots={r['id']:client.get('/api/admin/content/records/'+r['id']).json() for r in created}
    for id in [own[0],own[7],own[-1],ids[0],ids[-1],with_cover['id']]:
        index=ids.index(id);statements=[]
        def count(_conn,_cursor,statement,*_args):statements.append(statement)
        event.listen(engine,'before_cursor_execute',count)
        try:response=reader.get(BASE+'/'+id+'/neighbors')
        finally:event.remove(engine,'before_cursor_execute',count)
        assert response.status_code==200;data=response.json();assert data['context']=='global'
        assert (data['previous']['id'] if data['previous'] else None)==(ids[index-1] if index else None)
        assert (data['next']['id'] if data['next'] else None)==(ids[index+1] if index+1<len(ids) else None)
        assert all(sql.lstrip().upper().startswith('SELECT') for sql in statements)
        assert len(statements)<=8  # Authentication + bounded current/neighbor/cover queries.
        assert all('不能泄露' not in str(v) for v in data.values())
    for id in own:
        data=reader.get(BASE+'/'+id+'/neighbors').json()
        for item in [data['previous'],data['next']]:
            if item and item['id']==with_cover['id']:assert item['cover']['id']==media['id']
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(RecordRevision))==before
    for id,snapshot in snapshots.items():assert client.get('/api/admin/content/records/'+id).json()==snapshot
    for r in [draft,deleted,hidden]:assert reader.get(BASE+'/'+r['id']+'/neighbors').status_code==404
    reader.cookies.clear();assert reader.get(BASE+'/'+own[0]+'/neighbors').status_code==401
    assert client.get(BASE+'/'+str(uuid.uuid4())+'/neighbors').status_code==404


def test_single_visible_record_has_no_neighbors_and_feature_flag_is_enforced(client,monkeypatch):
    # Service boundary checked on a transaction-local synthetic collection; no global reset.
    from app.services import blog
    t=make_type(client);r=create_record(client,t)
    original=blog.readable
    monkeypatch.setattr(blog,'readable',lambda:original().where(ContentRecord.id==r['id']))
    result=client.get(BASE+'/'+r['id']+'/neighbors');assert result.status_code==200
    assert result.json()=={'context':'global','previous':None,'next':None}
    from dataclasses import replace
    app=client.app;previous=app.state.settings
    try:
        app.state.settings=replace(previous,dynamic_blog_enabled=False)
        assert client.get(BASE+'/'+r['id']+'/neighbors').status_code==200
    finally:app.state.settings=previous


def test_concurrent_display_date_change_cannot_make_current_record_its_own_neighbor(client):
    from app.services.blog import adjacent_records
    from test_content import update_payload
    t=make_type(client);record=create_record(client,t)
    with SessionLocal() as db:
        stale=db.get(ContentRecord,record['id'])
        result=write(client,'/records/'+record['id'],update_payload(record,display_date='9999-12-31'),'put')
        assert result.status_code==200
        data=adjacent_records(db,stale)
        assert all(not item or item['id']!=record['id'] for item in [data['previous'],data['next']])
