"""Export and provider context must share actual current field/template metadata."""
import io,json,zipfile
import pytest
from test_content import client,make_type,field,write,type_payload
from test_api import reset_limiter,SessionLocal
from app.exchange.context import context,specification_zip
from app.exchange.rules import merged
from app.exchange.parsers import parse,package


def test_real_context_and_export_follow_current_field_definitions(client):
    t=make_type(client,fields=[field('short_text',required=True,has_default=True,default_value='PRIVATE FIELD DEFAULT')|{'name':'真实自定义字段'}])
    with SessionLocal() as db:
        before=context(db,t['slug']);export=specification_zip(before)
    with zipfile.ZipFile(io.BytesIO(export)) as z:
        actual=json.loads(z.read('context.json'));assert actual==before
        assert 'PRIVATE FIELD DEFAULT' not in json.dumps(actual)
        assert actual['type']['fields'][0]['name']=='真实自定义字段'
        fid=actual['type']['fields'][0]['id']
        spec=actual['exchange_schema']['$defs']['Record']['properties']['values']
        assert spec['additionalProperties'] is False and spec['properties'][fid]['title']=='真实自定义字段'
        assert spec['properties'][fid]['x-required-on-publish'] is True
        assert parse(z.read('example.json'),'example.json')==parse(z.read('example.md'),'example.md')
        assert len(package(z.read('example-package.zip'))[0].records)==1
        assert all(s not in '\n'.join(z.namelist()) for s in ('.env','password','api-key'))
    updated=type_payload(t);updated['fields'][0]['name']='更新后的字段';assert write(client,'/types/'+t['id'],updated,'put').status_code==200
    with SessionLocal() as db:after=context(db,t['slug'])
    assert after['context_digest']!=before['context_digest'] and after['type']['version']==2
    assert after['type']['fields'][0]['name']=='更新后的字段'


def test_preference_order_cannot_remove_hard_constraints():
    result=merged({'require_start':True,'style':'全局'},{'style':'类型'},{'style':'模板'},{'style':'临时'})
    assert result['preferences']['style']=='临时' and result['preferences']['require_start'] is True
    assert 'draft-only' in result['hard_constraints']
    assert result['digest']==merged({'require_start':True,'style':'全局'},{'style':'类型'},{'style':'模板'},{'style':'临时'})['digest']
    with pytest.raises(ValueError):merged({'disable_csrf':True})


def test_private_field_defaults_are_applied_locally_without_exporting_them_to_models(client):
    from app.exchange.schemas import Exchange
    from app.exchange.preview import preview
    t=make_type(client,fields=[field('short_text',required=True,has_default=True,default_value='仅本地合成同行人')|{'name':'同行人'}])
    fid=t['fields'][0]['id']
    value=Exchange.model_validate({'format':'life-journal.exchange','version':1,'records':[{'key':'new','type_slug':t['slug'],'title':'合成创作候选','display_date':'2026-11-06','body':'本人提供的合成素材。'}]})
    with SessionLocal() as db:
        ctx=context(db,t['slug']);report=preview(db,value)
        assert '仅本地合成同行人' not in json.dumps(ctx,ensure_ascii=False)
        assert ctx['exchange_schema']['$defs']['Record']['properties']['values']['properties'][fid]['x-has-local-default'] is True
        assert report['valid'] and report['records'][0]['values'][fid]=='仅本地合成同行人'
        value.records[0].values={fid:'人工明确填写'}
        assert preview(db,value)['records'][0]['values'][fid]=='人工明确填写'
