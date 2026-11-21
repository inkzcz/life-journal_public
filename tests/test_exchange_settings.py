"""Admin CSRF/CAS and persisted preference precedence, with no secret values."""
import uuid
from test_content import client,make_type
from test_api import csrf,reset_limiter,SessionLocal
from app.exchange.context import context


def test_preferences_persist_by_scope_and_cannot_override_hard_constraints(client):
    t=make_type(client)
    endpoint='/api/admin/exchange/settings';old=client.get(endpoint).json()
    payload={'providers':old['providers'],'rules':{'global_preferences':{'require_start':True,'require_end':False},'content_types':{t['slug']:{'require_end':True}},'templates':{}},'expected_revision':old['revision']}
    assert client.put(endpoint,json=payload).status_code==403
    result=client.put(endpoint,headers=csrf(client),json=payload);assert result.status_code==200,result.text
    current=result.json();assert current['revision']==old['revision']+1
    assert client.get(endpoint).json()==current
    assert client.put(endpoint,headers=csrf(client),json=payload).status_code==409
    with SessionLocal() as db:
        value=context(db,t['slug'],layers=({'require_end':False},))
        assert value['rules']['preferences']['require_start'] is True
        assert value['rules']['preferences']['require_end'] is False
        assert 'draft-only' in value['rules']['hard_constraints']
    payload['expected_revision']=current['revision'];payload['rules']['global_preferences']={'status':'published'}
    assert client.put(endpoint,headers=csrf(client),json=payload).status_code==422
    # Restore only our synthetic global test configuration for unrelated cases.
    old['expected_revision']=current['revision'];old.pop('revision')
    assert client.put(endpoint,headers=csrf(client),json=old).status_code==200


def test_provider_never_accepts_plaintext_key_or_arbitrary_environment_reference(client):
    endpoint='/api/admin/exchange/settings';old=client.get(endpoint).json()
    provider={'id':str(uuid.uuid4()),'name':'离线测试配置','kind':'openai','base_url':'https://example.com/v1','model':'synthetic','key_env':'POSTGRES_PASSWORD','enabled':False}
    payload={'providers':[provider],'rules':old['rules'],'expected_revision':old['revision']}
    assert client.put(endpoint,headers=csrf(client),json=payload).status_code==422
    provider['key_env']='LJ_AI_KEY_SYNTHETIC';provider['api_key']='never-accept-this'
    assert client.put(endpoint,headers=csrf(client),json=payload).status_code==422
    del provider['api_key']
    assert client.put(endpoint,headers=csrf(client),json=payload).status_code==200
    saved=client.get(endpoint).json()
    assert 'api_key' not in str(saved) and saved['providers'][0]['key_env']=='LJ_AI_KEY_SYNTHETIC'
    old['expected_revision']=saved['revision'];old.pop('revision')
    assert client.put(endpoint,headers=csrf(client),json=old).status_code==200
