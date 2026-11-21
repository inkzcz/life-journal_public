"""Structural performance guards; timings live in the bounded PostgreSQL benchmark."""
from datetime import date
import uuid
from sqlalchemy import event,select
from test_archive import client,create_record
from test_content import make_type
from test_api import engine,SessionLocal
from app.content_models import ContentRecord,RecordRevision
from app.services.blog import page_records,readable,detail
from app.services.content import record_summaries


def test_list_query_count_is_constant_and_same_date_pagination_is_stable(client):
    t=make_type(client);ids=[]
    with SessionLocal() as db:
        for n in range(85):
            id=str(uuid.uuid4());ids.append(id);db.add(ContentRecord(id=id,type_id=t['id'],schema_version=t['version'],title='合成同日期 '+str(n),body='不能完整加载的正文'*1000,display_date=date(2026,10,20),status='published',values={}))
        db.commit()
    def capture(db,action):
        statements=[]
        def listener(conn,cursor,sql,params,context,many):statements.append(sql)
        event.listen(engine,'before_cursor_execute',listener)
        try:result=action()
        finally:event.remove(engine,'before_cursor_execute',listener)
        return result,statements
    with SessionLocal() as db:
        q=readable().where(ContentRecord.type_id==t['id']);seen=[]
        for page in range(1,6):
            result,sql=capture(db,lambda:page_records(db,q,page,20));seen.extend(r['id'] for r in result['items'])
            assert len(sql)==3 and result['total']==85
            assert all(len(r['excerpt'])<=220 for r in result['items'])
            assert all('content_records.values' not in s for s in sql)
        assert seen==sorted(ids) and len(seen)==len(set(seen))
        records,sql=capture(db,lambda:record_summaries(db,select(ContentRecord).where(ContentRecord.type_id==t['id']).limit(50)))
        assert len(records)==50 and len(sql)==1
        assert 'content_records.body' not in sql[0] and 'content_records.values' not in sql[0]


def test_history_index_defers_snapshots_without_changing_current_record(client):
    from test_archive import C
    t=make_type(client);r=create_record(client,t)
    with SessionLocal() as db:
        # Existing create snapshot remains; add 20 large synthetic revisions.
        actor=db.scalar(select(RecordRevision.actor_id).where(RecordRevision.record_id==r['id']))
        for n in range(2,22):db.add(RecordRevision(record_id=r['id'],number=n,actor_id=actor,snapshot={'body':'合成历史'*10000}))
        db.commit()
    sql=[]
    def listener(conn,cursor,statement,params,context,many):sql.append(statement)
    event.listen(engine,'before_cursor_execute',listener)
    try:response=client.get('/api/admin/recovery/history/'+r['id'])
    finally:event.remove(engine,'before_cursor_execute',listener)
    assert response.status_code==200 and response.json()['current']['body']==r['body']
    assert response.json()['total']==21 and len(response.json()['items'])==20
    index=[s for s in sql if 'FROM record_revisions' in s and 'count(' not in s]
    assert len(index)==1 and 'record_revisions.snapshot' not in index[0]


def test_section_types_are_loaded_in_one_batch(client):
    from app.blog_models import Section,SectionType
    from app.services.blog import sections_data
    t=make_type(client)
    with SessionLocal() as db:
        for n in range(30):
            s=Section(id=str(uuid.uuid4()),name='合成栏目',slug='performance-'+uuid.uuid4().hex);db.add(s);db.flush();db.add(SectionType(section_id=s.id,type_id=t['id']))
        db.commit()
        rows=list(db.scalars(select(Section)));sql=[]
        def listener(conn,cursor,statement,params,context,many):sql.append(statement)
        event.listen(engine,'before_cursor_execute',listener)
        try:items=sections_data(db,rows)
        finally:event.remove(engine,'before_cursor_execute',listener)
        assert len(sql)==1 and sum(t['id'] in s['type_ids'] for s in items)==30


def test_editor_marker_protocol_projects_scalar_without_loading_historical_body(client):
    from app.services.experiences import syntax_version
    t=make_type(client);r=create_record(client,t)
    sql=[]
    def listener(conn,cursor,statement,params,context,many):sql.append(statement)
    with SessionLocal() as db:
        record=db.get(ContentRecord,r['id'])
        event.listen(engine,'before_cursor_execute',listener)
        try:assert syntax_version(db,record)==1
        finally:event.remove(engine,'before_cursor_execute',listener)
    assert len(sql)==1
    import re
    assert 'record_revisions.actor_id' not in sql[0]
    assert not re.match(r'SELECT\s+record_revisions\.snapshot\s*(?:,|\s+(?:AS|FROM)\b)',sql[0],re.I)
    assert 'record_revisions.number' in sql[0]
