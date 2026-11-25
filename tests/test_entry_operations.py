"""Synthetic card transfers use one commit, real parser and immutable revisions."""
import uuid
import pytest
from test_content import client,write,record_payload
from test_api import SessionLocal,csrf,reset_limiter
from app.content_models import ContentRecord
from app.services.experiences import serialize,entries


def setup(client,kind='m'):
    t=write(client,'/types',{'slug':'synthetic-'+uuid.uuid4().hex[:12],'name':'合成文章','fields':[]}).json()
    e={'id':str(uuid.uuid4()),'kind':kind,'name':'合成卡片','fields':{'description':'保留换行\n原文','historical_extra':'保留的扩展字段'},'media_ids':[]}
    if kind=='t':e['fields'].update(transport_type='高铁',departure='重庆',destination='成都',departure_at='2026-11-13T15:43+08:00',arrival_at='2026-11-13T17:36+08:00',departure_zone='Asia/Shanghai',arrival_zone='Asia/Shanghai')
    a=write(client,'/records',(record_payload(t,article={'travel_enabled':False})|{'body_format':2,'body':'前文\n\n'+serialize(e)+'\n\n后文'})).json()
    b=write(client,'/records',(record_payload(t,article={'travel_enabled':True})|{'body_format':2,'body':'目标原文\n'})).json()
    return a,b,e


def operation(a,b,e,kind='copy'):
    return {'operation':kind,'target_id':b['id'],'entry_id':e['id'],'request_id':str(uuid.uuid4()),'source_revision':a['revision'],'target_revision':b['revision']}


@pytest.mark.parametrize('kind',list('lfmsgt'))
@pytest.mark.parametrize('mode',['copy','move'])
def test_copy_move_preserve_payload_and_original_text_with_idempotent_replay(client,kind,mode):
    a,b,e=setup(client,kind);data=operation(a,b,e,mode)
    path='/api/admin/content/records/'+a['id']+'/entry-operation'
    response=client.post(path,headers=csrf(client),json=data);assert response.status_code==200,response.text
    receipt=response.json()
    with SessionLocal() as db:
        source=db.get(ContentRecord,a['id']);target=db.get(ContentRecord,b['id'])
        copied=entries(target.body)[0]
        assert {k:v for k,v in copied.items() if k!='id'}=={k:v for k,v in e.items() if k!='id'}
        assert (copied['id']==e['id']) is (mode=='move')
        assert target.body.startswith(b['body']) and '前文' in source.body and '后文' in source.body
        if mode=='copy':assert source.body==a['body']
        else:assert entries(source.body)==[]
    again=client.post(path,headers=csrf(client),json=data);assert again.status_code==200,again.text
    assert again.json()['entry_id']==receipt['entry_id'] and again.json()['replayed'] is True
    with SessionLocal() as db:assert len(entries(db.get(ContentRecord,b['id']).body))==1


def test_conflict_and_csrf_never_remove_source(client):
    a,b,e=setup(client);data=operation(a,b,e,'move');path='/api/admin/content/records/'+a['id']+'/entry-operation'
    assert client.post(path,json=data).status_code==403
    data['target_revision']+=1
    assert client.post(path,headers=csrf(client),json=data).status_code==409
    with SessionLocal() as db:assert db.get(ContentRecord,a['id']).body==a['body']


def test_actual_parser_ignores_marker_example_in_fence(client):
    a,b,e=setup(client)
    with SessionLocal() as db:
        source=db.get(ContentRecord,a['id']);source.body='```text\n'+serialize(e)+'\n```\n';db.commit()
    response=client.post('/api/admin/content/records/'+a['id']+'/entry-operation',headers=csrf(client),json=operation(a,b,e,'move'))
    assert response.status_code==404
    with SessionLocal() as db:assert db.get(ContentRecord,b['id']).body==b['body']


def test_same_article_copy_inserts_after_original_and_uses_new_uuid(client):
    a,_,e=setup(client)
    result=client.post('/api/admin/content/records/'+a['id']+'/entry-operation',headers=csrf(client),json=operation(a,a,e))
    assert result.status_code==200,result.text
    with SessionLocal() as db:
        body=db.get(ContentRecord,a['id']).body;cards=entries(body)
        assert len(cards)==2 and cards[0]['id']==e['id'] and cards[1]['id']!=e['id']
        assert body.startswith('前文') and body.endswith('后文')


def test_second_snapshot_failure_rolls_back_both_bodies_and_versions(client,monkeypatch):
    from app.services import entry_operations
    a,b,e=setup(client);original=entry_operations.revision_snapshot;calls=[]
    def fail(db,record,actor):
        calls.append(record.id)
        if len(calls)==2:raise RuntimeError('Synthetic transaction failure')
        return original(db,record,actor)
    monkeypatch.setattr(entry_operations,'revision_snapshot',fail)
    with pytest.raises(RuntimeError,match='Synthetic'):
        client.post('/api/admin/content/records/'+a['id']+'/entry-operation',headers=csrf(client),json=operation(a,b,e,'move'))
    with SessionLocal() as db:
        for before in (a,b):
            after=db.get(ContentRecord,before['id']);assert after.body==before['body'] and after.revision==before['revision']


def test_transfer_keeps_shared_media_references_after_source_soft_delete(client):
    from test_archive import upload
    from test_content import update_payload
    from sqlalchemy import select
    from app.experience_models import ExperienceMedia
    asset=upload(client).json()
    a,b,e=setup(client)
    e['media_ids']=[asset['id']]
    a=write(client,'/records/'+a['id'],update_payload(a,body='前文\n\n'+serialize(e)+'\n\n后文'),'put').json()
    response=client.post('/api/admin/content/records/'+a['id']+'/entry-operation',headers=csrf(client),json=operation(a,b,e,'move'))
    assert response.status_code==200,response.text
    receipt=response.json()
    deleted=client.request('DELETE','/api/admin/content/records/'+a['id'],headers=csrf(client),json={'expected_revision':receipt['source_revision']})
    assert deleted.status_code==200,deleted.text
    with SessionLocal() as db:
        ref=db.get(ExperienceMedia,(b['id'],e['id'],asset['id']))
        assert ref and ref.active and ref.position==0
    assert client.get('/api/library-media/'+asset['id']+'/original').status_code==200
    from app.services.resource_usage import assert_media_unused
    from fastapi import HTTPException
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as protected:assert_media_unused(db,asset['id'])
        assert protected.value.status_code==409


def test_picker_is_bounded_and_excludes_current_deleted_and_disabled_targets(client):
    from app.content_models import ContentType
    a,b,e=setup(client)
    result=client.get('/api/admin/content/entry-targets',params={'q':b['title'],'exclude_id':a['id']}).json()
    assert result['page_size']==20 and len(result['items'])<=20
    assert all('body' not in r and 'values' not in r for r in result['items'])
    assert a['id'] not in {r['id'] for r in result['items']}
    with SessionLocal() as db:
        db.get(ContentType,b['type_id']).active=False;db.commit()
    response=client.post('/api/admin/content/records/'+a['id']+'/entry-operation',headers=csrf(client),json=operation(a,b,e))
    assert response.status_code==409


def test_parallel_retries_have_one_durable_transfer(client):
    from concurrent.futures import ThreadPoolExecutor
    from app.routers.content import EntryOperation
    from app.services.entry_operations import operate
    from app.content_models import RecordRevision
    a,b,e=setup(client);data=EntryOperation.model_validate(operation(a,b,e))
    with SessionLocal() as db:actor=db.get(RecordRevision,(a['id'],a['revision'])).actor_id
    def attempt(_):
        with SessionLocal() as db:
            result=operate(db,a['id'],data,actor);db.commit();return result
    with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(attempt,range(2)))
    assert len({r['entry_id'] for r in results})==1
    assert sorted(r['replayed'] for r in results)==[False,True]
    with SessionLocal() as db:assert len(entries(db.get(ContentRecord,b['id']).body))==1


def test_transfers_preserve_legal_name_whitespace_and_crlf_without_touching_other_blocks(client):
    a,b,e=setup(client);e['name']='  合成名称  '
    with SessionLocal() as db:
        source=db.get(ContentRecord,a['id']);source.body='原文\r\n\r\n'+serialize(e).replace('\n','\r\n')+'\r\n\r\n保留结尾';db.commit()
    response=client.post('/api/admin/content/records/'+a['id']+'/entry-operation',headers=csrf(client),json=operation(a,b,e,'move'))
    assert response.status_code==200,response.text
    import json
    with SessionLocal() as db:
        source=db.get(ContentRecord,a['id']);target=db.get(ContentRecord,b['id'])
        assert source.body=='原文\r\n\r\n\r\n保留结尾'
        line=next(line for line in target.body.splitlines() if 'media_ids' in line)
        assert json.loads(line)['name']==e['name']
