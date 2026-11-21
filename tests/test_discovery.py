"""Synthetic PostgreSQL archive, catalog, revision and bounded-query regressions."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import pytest
from sqlalchemy import select,func,event,text
from fastapi.testclient import TestClient
from test_api import app,engine,SessionLocal,login,csrf,reset_limiter
from test_content import client,write,make_type,field,record_payload as original_payload,update_payload,type_payload
from app.main import create_app
from app.tag_models import Tag,RecordTag,JournalTagIdentity
from app.content_models import ContentRecord,RecordRevision
from app.services import tags


def record_payload(t,values=None,**changes):
    return {**original_payload(t,values),**changes}

def tag(c,name):
    r=c.post('/api/admin/tags',json={'name':name},headers=csrf(c));assert r.status_code==200,r.text
    return r.json()

def request(c,path,data,method='post'):
    return c.request(method.upper(),'/api/admin/tags'+path,json=data,headers=csrf(c))

def test_catalog_unicode_limits_merge_and_restore(client):
    suffix=uuid.uuid4().hex[:8];a=tag(client,'  日本　旅行 '+suffix+'  ')
    assert tag(client,'日本 旅行 '+suffix)['id']==a['id']
    assert tag(client,'ＡＢＣ'+suffix)['id']==tag(client,'abc'+suffix)['id']
    assert tag(client,'Cafe\u0301'+suffix)['id']==tag(client,'CAFÉ'+suffix)['id']
    for bad in ['', ' '*10,'x'*41,'a\u200bb']:
        assert request(client,'',{'name':bad}).status_code==422
    b=tag(client,'目标 '+suffix);t=make_type(client)
    r=write(client,'/records',record_payload(t,tag_ids=[a['id'],b['id']])).json()
    assert len(r['tags'])==2
    assert client.delete('/api/admin/tags/'+a['id'],headers=csrf(client)).status_code==409
    assert request(client,'/'+a['id'],{'name':b['name']},'put').status_code==409
    assert request(client,'/'+a['id']+'/merge',{'target_id':b['id'],'confirm':False}).status_code==422
    assert request(client,'/'+a['id']+'/merge',{'target_id':b['id'],'confirm':True}).status_code==200
    current=client.get('/api/admin/content/records/'+r['id']).json()
    assert current['revision']==r['revision']+1 and current['tag_ids']==[b['id']]
    assert write(client,'/records/'+r['id'],update_payload(r,tag_ids=[]),'put').status_code==409
    # Full restore resolves old source IDs through the merge tombstone, deduplicated.
    from app.services.recovery import restore_history
    from app.recovery_schemas import HistoryRestore
    with SessionLocal() as db:
        from app.services.archive import write_lock
        write_lock(db);row=db.get(ContentRecord,r['id']);old=db.get(RecordRevision,(r['id'],1))
        payload=HistoryRestore(expected_revision=row.revision,scope='full',confirmation='恢复为新草稿')
        restored=restore_history(db,row,old,payload,old.actor_id);db.commit()
        assert restored['tag_ids']==[b['id']] and restored['status']=='draft'
    assert write(client,'/records',record_payload(t,tag_ids=[b['id']]*2)).status_code==422
    assert write(client,'/records',record_payload(t,tag_ids=[str(uuid.uuid4())])).status_code==409
    many=[tag(client,'多标签'+suffix+str(n))['id'] for n in range(11)]
    assert write(client,'/records',record_payload(t,tag_ids=many)).status_code==422
    unused=tag(client,'未使用'+suffix)
    assert client.delete('/api/admin/tags/'+unused['id'],headers=csrf(client)).status_code==200
    # v5 deletion keeps a tombstone: an old editor/name request cannot revive it.
    assert client.post('/api/admin/tags',headers=csrf(client),json={'name':unused['name']}).status_code==409


def test_archive_visibility_search_and_combination(client):
    s=uuid.uuid4().hex[:8];a=tag(client,'京都'+s);b=tag(client,'秋天'+s)
    t=make_type(client,[field(searchable=True),field('long_text',position=1)])
    f,g=[x['id'] for x in t['fields']]
    r=write(client,'/records',record_payload(t,{f:'可搜京都'+s,g:'隐藏搜索字段'+s},title='测试'+s,body='正文含百分号%与下划线_',display_date='2023-11-02',tag_ids=[a['id'],b['id']])).json()
    def search(**kw):
        response=client.get('/api/blog/archive',params={'type':t['id'],**kw});assert response.status_code==200,response.text;return response.json()
    assert search(q='可搜京都'+s)['total']==1
    assert search(q='隐藏搜索字段'+s)['total']==0
    assert search(q='%')['total']==1 and search(q='_')['total']==1
    assert search(q="%' OR 1=1 --")['total']==0
    assert search(q='测试'+s,year=2023,tag=[a['id'],b['id']])['total']==1
    assert search(year=2026)['total']==0
    assert search(tag=[a['id'],str(uuid.uuid4())])['total']==0
    assert search(page=999)['items']==[]
    assert client.get('/api/blog/archive',params={'page_size':10000}).status_code==422
    for status,deleted in [('draft',False),('published',True)]:
        x=write(client,'/records',record_payload(t,title='不可见'+s,status=status,tag_ids=[a['id']])).json()
        if deleted:assert write(client,'/records/'+x['id'],{'expected_revision':x['revision']},'delete').status_code==200
    assert search()['total']==1
    facets=client.get('/api/blog/archive/facets').json()
    assert next(x for x in facets['tags'] if x['id']==a['id'])['count']==1
    assert client.get('/api/blog/records/'+r['id']).json()['tags']==r['tags']
    assert write(client,'/types/'+t['id'],type_payload(t,active=False),'put').status_code==200
    assert search()['total']==0
    assert not any(x['id']==a['id'] for x in client.get('/api/blog/archive/facets').json()['tags'])


def test_legacy_mapping_and_transaction_rollback(client):
    # Explicit archival fixture; no legacy router in production.
    from legacy_backend import journals,media
    client.app.include_router(journals.router);client.app.include_router(media.router)
    name='兼容 '+uuid.uuid4().hex[:8]
    j=client.post('/api/journals',json={'title':'虚构旧日记','content':'原正文','tags':[name],'entry_date':'2020-01-01'},headers=csrf(client)).json()
    with SessionLocal() as db:
        mapping=db.get(JournalTagIdentity,(j['id'],name));assert mapping
        tid=mapping.tag_id
        from app.services.archive import write_lock
        write_lock(db);t=tags.identity(db,'回滚标签'+uuid.uuid4().hex);id=t.id;db.rollback();assert db.get(Tag,id) is None
    assert request(client,'/'+tid,{'name':'新目录名 '+uuid.uuid4().hex[:8]},'put').status_code==200
    assert client.get('/api/journals/'+str(j['id'])).json()['tags']==[name]
    assert client.put('/api/journals/'+str(j['id']),json={'title':'继续编辑','content':'仍保留','tags':[name]},headers=csrf(client)).status_code==200
    with SessionLocal() as db:assert db.get(JournalTagIdentity,(j['id'],name)).tag_id==tid
    assert client.get('/api/journals/page',params={'tag':name}).json()['total']>=1
    assert client.delete('/api/journals/'+str(j['id']),headers=csrf(client)).status_code==200
    with SessionLocal() as db:assert db.get(JournalTagIdentity,(j['id'],name)) is None


def test_concurrent_same_tag_and_record_conflict(client):
    name='并发 '+uuid.uuid4().hex[:8]
    def create(_):
        with SessionLocal() as db:
            from app.services.archive import write_lock
            write_lock(db);t=tags.identity(db,name);id=t.id;db.commit();return id
    with ThreadPoolExecutor(2) as pool:ids=list(pool.map(create,range(2)))
    assert ids[0]==ids[1]
    t=make_type(client);r=write(client,'/records',record_payload(t,status='draft',tag_ids=ids[:1])).json()
    first=write(client,'/records/'+r['id'],update_payload(r,tag_ids=[]),'put');assert first.status_code==200
    assert write(client,'/records/'+r['id'],update_payload(r,tag_ids=ids[:1]),'put').status_code==409
    # Legacy client omits tag_ids: retain current tags.
    r=first.json();r=write(client,'/records/'+r['id'],update_payload(r,tag_ids=ids[:1]),'put').json()
    assert write(client,'/records/'+r['id'],update_payload(r,title='旧客户端'),'put').json()['tag_ids']==ids[:1]


def test_thousand_records_bounded_queries(client):
    t=make_type(client);other=make_type(client);label=tag(client,'千条 '+uuid.uuid4().hex[:8]);second=tag(client,'组合 '+uuid.uuid4().hex[:8])
    from datetime import date
    with SessionLocal() as db:
        for n in range(1000):
            id=str(uuid.uuid4());db.add(ContentRecord(id=id,type_id=t['id'] if n%2 else other['id'],schema_version=1,title='京都合成 '+str(n),body='长正文'*1000,display_date=date(2020+n%5,1,1),status='published',values={}))
            db.flush();db.add(RecordTag(record_id=id,tag_id=label['id']))
            if n%3==0:db.add(RecordTag(record_id=id,tag_id=second['id']))
        db.commit()
    statements=[]
    def count(conn,cursor,statement,parameters,context,many):statements.append(statement)
    import time
    started=time.monotonic()
    event.listen(engine,'before_cursor_execute',count)
    try:
        response=client.get('/api/blog/archive',params={'type':t['id'],'q':'京都','tag':label['id'],'page':2})
        assert response.status_code==200,response.text
    finally:event.remove(engine,'before_cursor_execute',count)
    d=response.json();assert d['total']==500 and len(d['items'])==20
    assert all('body' not in r and len(r['excerpt'])<=220 for r in d['items'])
    assert len(statements)<=8,statements  # session auth + timeout + count/page + two batched associations
    assert sum('FROM content_records' in s for s in statements)<=2
    assert [x['id'] for x in d['items']]==sorted(x['id'] for x in d['items'])
    elapsed=time.monotonic()-started;query_count=len(statements)
    combined=client.get('/api/blog/archive',params={'type':t['id'],'year':2024,'q':'京都','tag':[label['id'],second['id']]}).json()
    assert combined['total']==sum(n%2==1 and n%5==4 and n%3==0 for n in range(1000))
    import os,json
    from pathlib import Path
    if os.getenv('DISCOVERY_PERF_REPORT'):
        Path(os.environ['DISCOVERY_PERF_REPORT']).write_text(json.dumps({'records':1000,'types':2,'years':5,'page_size':20,'filtered_total':500,'query_count_including_auth':query_count,'seconds':round(elapsed,4),'response_bytes':len(response.content),'combined_total':combined['total']},indent=2)+'\n')


def test_auth_flag_csrf_and_reader(client):
    from app.models import User
    from app.security import ph
    from test_api import PASSWORD
    with SessionLocal() as db:
        name='reader-'+uuid.uuid4().hex;db.add(User(username=name,password_hash=ph.hash(PASSWORD)));db.commit()
    enabled=create_app(replace(app.state.settings,dynamic_blog_enabled=True))
    with TestClient(enabled,base_url='https://testserver') as c:
        assert c.get('/api/blog/archive').status_code==401
        c.post('/api/auth/login',json={'username':name,'password':PASSWORD},headers=csrf(c))
        assert c.get('/api/blog/archive').status_code==200
        assert c.get('/api/admin/tags').status_code==403
        assert c.post('/api/admin/tags',json={'name':'越权'},headers=csrf(c)).status_code==403
    assert client.post('/api/admin/tags',json={'name':'无CSRF'}).status_code==403
    with TestClient(app,base_url='https://testserver') as c:
        login(c);assert c.get('/api/blog/archive').status_code==200;assert c.get('/api/admin/tags').status_code==200
        assert c.get('/api/journals/page').status_code==200


def test_merge_failure_is_atomic_and_database_uniqueness(client,monkeypatch):
    from sqlalchemy.exc import IntegrityError
    from app.services import content
    from app.services.archive import write_lock
    a=tag(client,'事务源'+uuid.uuid4().hex[:8]);b=tag(client,'事务目标'+uuid.uuid4().hex[:8]);t=make_type(client)
    r=write(client,'/records',record_payload(t,tag_ids=[a['id']])).json()
    def fail(*args):raise RuntimeError('synthetic snapshot failure')
    with SessionLocal() as db:
        actor=db.get(RecordRevision,(r['id'],1)).actor_id
        with monkeypatch.context() as m:
            m.setattr(content,'revision_snapshot',fail)
            with pytest.raises(RuntimeError,match='synthetic'):tags.merge(db,a['id'],b['id'],actor)
        db.rollback()
        assert db.get(Tag,a['id']).merged_into is None
        assert db.get(RecordTag,(r['id'],a['id'])) and db.get(RecordTag,(r['id'],b['id'])) is None
        assert db.get(ContentRecord,r['id']).revision==1
        assert db.get(RecordRevision,(r['id'],2)) is None
        db.add(RecordTag(record_id=r['id'],tag_id=a['id']))
        with pytest.raises(IntegrityError):db.flush()
        db.rollback();source=db.get(Tag,a['id'])
        db.add(Tag(id=str(uuid.uuid4()),name='重复身份',normalized_name=source.normalized_name))
        with pytest.raises(IntegrityError):db.flush()
        db.rollback()


def test_pre_tags_snapshot_restoration_keeps_current_tags(client):
    from app.services.recovery import restore_history
    from app.recovery_schemas import HistoryRestore
    from app.services.archive import write_lock
    a=tag(client,'早期'+uuid.uuid4().hex[:8]);b=tag(client,'当前'+uuid.uuid4().hex[:8]);t=make_type(client)
    r=write(client,'/records',record_payload(t,tag_ids=[a['id']])).json()
    updated=write(client,'/records/'+r['id'],update_payload(r,tag_ids=[b['id']]),'put').json()
    with SessionLocal() as db:
        write_lock(db);old=db.get(RecordRevision,(r['id'],1));old.snapshot={k:v for k,v in old.snapshot.items() if k not in {'tags','tag_ids'}};db.flush()
        current=db.get(ContentRecord,r['id'])
        result=restore_history(db,current,old,HistoryRestore(expected_revision=updated['revision'],scope='content',confirmation='恢复为新草稿'),old.actor_id)
        db.commit();assert result['tag_ids']==[b['id']] and result['status']=='draft'
