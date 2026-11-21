"""Preserve authored syntax without asking a model to reproduce UUIDs."""
import json,uuid
import pytest
from test_content import client,make_type
from test_api import csrf,reset_limiter,SessionLocal,MEDIA_DIR
from test_exchange_invocations import configure,request_data,output,restore_synthetic_settings
from app.exchange import protected_source,transport
from app.exchange.schemas import Exchange


def test_multiline_marks_dates_and_code_examples_use_the_existing_parser():
    class NoResources:
        def get(self,*args):raise AssertionError('No declared resource should be read')
    body='开场。\r\n\r\n## 2026-10-03\r\n\r\n- @l 成都 @f 合成餐厅\r\n  - 味道很好。\r\n\r\n```md\n@f 仅为代码示例\n```\n结尾。'
    plan=protected_source.prepare(NoResources(),body)
    assert '@l 成都' not in plan.body and '@f 合成餐厅' not in plan.body
    assert '@f 仅为代码示例' in plan.body and '味道很好' in plan.body
    assert plan.restore(plan.body)==body
    for bad in (plan.body.replace(plan.fragments[0][0],''),plan.body+plan.fragments[0][0],plan.body.replace(plan.fragments[0][0],plan.fragments[1][0])):
        with pytest.raises(ValueError):plan.restore(bad)
    with pytest.raises(ValueError):plan.restore('```md\n'+plan.body+'\n```')
    altered=plan.body.replace('开场。','更自然的开场。')
    assert plan.restore(altered)==body.replace('开场。','更自然的开场。')


def test_full_body_polish_preserves_real_private_photo_and_place_without_sending_ids(client,monkeypatch):
    from test_exchange_jobs import prepare,confirm
    t=make_type(client);preview,_,_=prepare(client,t);done=confirm(client,preview);assert done.status_code==200
    rid=done.json()['result_ids'][0];article=client.get('/api/admin/content/records/'+rid).json()
    provider,revision=configure(client);data=request_data(provider,revision,t['slug']);data.update(action='polish',body=article['body'],body_format=2,display_date=article['display_date'])
    media_ids=[p['media_id'] for p in article['life']['photos']];seen=[]
    def fake(provider,suffix,payload):
        material=json.loads(payload['messages'][-1]['content']);seen.append(material)
        assert all(id not in material['body'] for id in media_ids)
        assert ':::lj-media-v1' not in material['body'] and '{{lj-keep-' in material['body']
        facts=json.dumps(material['protected_fragments'],ensure_ascii=False)
        assert '合成小馆甲' in facts and '2026-10-01' in facts
        assert '#place:' not in facts and all(id not in facts for id in media_ids)
        result=output(t['slug']);result['records'][0]['body']=material['body']
        return {'message':{'content':json.dumps(result)}}
    monkeypatch.setattr(transport,'post',fake)
    response=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data)
    assert response.status_code==200,response.text
    result=response.json();assert result['preview']['valid']
    assert result['preview']['input']['records'][0]['body']==article['body']
    assert {m['existing_id'] for m in result['preview']['input']['media']}==set(media_ids)
    assert client.get('/api/admin/content/records/'+rid).json()['body']==article['body']
    assert len(seen)==1


def test_lost_preservation_token_rejects_output_and_never_modifies_article(client,monkeypatch):
    t=make_type(client);provider,revision=configure(client);data=request_data(provider,revision,t['slug']);data.update(action='polish',body='## 2026-10-03\n\n- @f 合成餐厅\n  - 描述不得丢失。')
    monkeypatch.setattr(transport,'post',lambda *args:{'message':{'content':json.dumps(output(t['slug']))}})
    response=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data)
    assert response.status_code==502,response.text
    replay=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data)
    assert replay.status_code==200 and replay.json()['state']=='failed' and replay.json()['job_id'] is None


def test_legacy_literal_private_block_is_not_silently_activated():
    class NoResources:
        def get(self,*args):raise AssertionError('Legacy literal must be rejected before resource reads')
    text=':::lj-media-v1\n'+json.dumps({'id':str(uuid.uuid4())})+'\n:::\n'
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as caught:protected_source.prepare(NoResources(),text,1)
    assert caught.value.status_code==422


def test_date_only_fragment_cannot_be_hidden_in_code_or_html():
    class NoResources:
        def get(self,*args):raise AssertionError('No resource access needed')
    plan=protected_source.prepare(NoResources(),'## 2026-10-03\n\n普通文字。')
    assert plan.restore(plan.body)=='## 2026-10-03\n\n普通文字。'
    for wrapped in ('```md\n'+plan.body+'\n```','<div>\n'+plan.body+'\n</div>','`'+plan.body+'`'):
        with pytest.raises(ValueError):plan.restore(wrapped)


def test_fact_hints_only_include_selected_authored_text_not_resource_ids_or_code():
    class NoResources:
        def get(self,*args):raise AssertionError('No resource access needed')
    body='## 2026-10-03\n\n- @f 明确选择的餐厅\n\n```md\n@f 代码中的示例不应成为事实\n```'
    plan=protected_source.prepare(NoResources(),body)
    facts=json.dumps(plan.hints,ensure_ascii=False)
    assert '2026-10-03' in facts and '明确选择的餐厅' in facts
    assert '代码中的示例' not in facts
    assert plan.restore(plan.body)==body


def test_unified_cards_are_opaque_to_model_and_exactly_restored_with_media(client):
    from test_archive import upload
    from test_experiences import card
    from app.services.experiences import serialize
    from app.exchange.protected_source import prepare
    from test_api import SessionLocal
    m=upload(client).json();e=card('m','合成受保护电影',fields={'cinema':'合成影院'},media_ids=[m['id']]);body='原文\n\n'+serialize(e)+'\n\n结尾'
    with SessionLocal() as db:plan=prepare(db,body,2)
    assert e['id'] not in plan.body and m['id'] not in plan.body and 'lj-entry' not in plan.body
    assert plan.restore(plan.body)==body
    assert any(x['existing_id']==m['id'] for x in plan.media)
    import pytest
    with pytest.raises(ValueError):plan.restore(plan.body+'\n\n'+serialize(e))
