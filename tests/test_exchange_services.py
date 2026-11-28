"""Revisioned API lifecycle and legacy JSON round trip, no external requests."""
import uuid
from test_content import client
from test_api import csrf,reset_limiter,SessionLocal
from app.exchange import transport
from app.exchange.settings import read


def test_services_share_credentials_keep_history_ids_and_dangling_defaults(client,monkeypatch):
    path='/api/admin/exchange/settings';old=client.get(path).json();service_id=str(uuid.uuid4());model_id=str(uuid.uuid4())
    service={'id':service_id,'name':'Synthetic shared','kind':'anthropic','base_url':'https://synthetic.example/v1','key_env':'LJ_AI_KEY_SYNTHETIC','enabled':False}
    model={'id':model_id,'service_id':service_id,'name':'Synthetic model','model':'mock','kind':'ollama','base_url':'http://127.0.0.1:11434','enabled':True}
    payload={'providers':[model],'services':[service],'task_defaults':{'summary':model_id},'default_provider':model_id,'rules':old['rules'],'expected_revision':old['revision']}
    current=client.put(path,headers=csrf(client),json=payload);assert current.status_code==200,current.text
    saved=current.json()
    try:
        with SessionLocal() as db:
            revision,config=read(db);effective=config.profiles()[0]
            assert revision==saved['revision'] and str(effective.id)==model_id and not effective.enabled
            assert effective.kind=='anthropic' and effective.key_env=='LJ_AI_KEY_SYNTHETIC'
        # Listing a disabled service cannot touch DNS/network.
        monkeypatch.setattr(transport,'get',lambda *args:(_ for _ in ()).throw(AssertionError('disabled must not send')))
        result=client.get(f'/api/admin/exchange/ai/services/{service_id}/models?expected_revision={saved["revision"]}')
        assert result.status_code==422
        payload={k:v for k,v in saved.items() if k!='revision'};payload['expected_revision']=saved['revision'];payload['providers']=[]
        current=client.put(path,headers=csrf(client),json=payload);assert current.status_code==200,current.text
        saved=current.json();assert saved['task_defaults']['summary']==model_id and saved['default_provider']==model_id
    finally:
        old['expected_revision']=saved['revision'];old.pop('revision');assert client.put(path,headers=csrf(client),json=old).status_code==200


def test_presets_and_model_listing_are_bounded_explicit_and_revision_guarded(client,monkeypatch):
    presets=client.get('/api/admin/exchange/ai/presets').json()
    assert len(presets['items'])==12 and presets['streaming'] is False and set(presets['tasks'])=={'generate','polish','expand','continue','title','summary','tags','fields','trip','review'}
    assert all(p['docs'].startswith('https://') for p in presets['items'])
    path='/api/admin/exchange/settings';old=client.get(path).json();service_id=str(uuid.uuid4());seen=[]
    payload={'providers':[],'services':[{'id':service_id,'name':'Mock service','kind':'gemini','base_url':'https://synthetic.example/v1beta','key_env':'LJ_AI_KEY_SYNTHETIC','enabled':True}],'expected_revision':old['revision']}
    monkeypatch.setattr(transport,'resolve_endpoint',lambda provider:(provider.base_url,['8.8.8.8'],False))
    current=client.put(path,headers=csrf(client),json=payload);assert current.status_code==200,current.text;saved=current.json()
    try:
        def fetch(provider,suffix):seen.append((provider.kind,suffix));return {'models':[{'name':'models/mock','supportedGenerationMethods':['generateContent']}]}
        monkeypatch.setattr(transport,'get',fetch)
        result=client.get(f'/api/admin/exchange/ai/services/{service_id}/models?expected_revision={saved["revision"]-1}')
        assert result.status_code==409 and not seen
        result=client.get(f'/api/admin/exchange/ai/services/{service_id}/models?expected_revision={saved["revision"]}')
        assert result.status_code==200 and result.json()['items']==[{'id':'mock','name':'mock'}] and seen==[('gemini','/models')]
    finally:
        old['expected_revision']=saved['revision'];old.pop('revision');assert client.put(path,headers=csrf(client),json=old).status_code==200


# Exercise native serialization through the real idempotency and preview pipeline.
import json
import pytest
from test_content import make_type
from test_exchange_invocations import output,request_data

@pytest.mark.parametrize('kind',['openai','ollama','anthropic','gemini'])
def test_shared_service_native_call_creates_only_preview_and_replays_without_network(client,monkeypatch,kind):
    old=client.get('/api/admin/exchange/settings').json();sid=str(uuid.uuid4());mid=str(uuid.uuid4());t=make_type(client)
    service={'id':sid,'name':'Synthetic native service','kind':kind,'base_url':'https://synthetic.example/v1','key_env':'LJ_AI_KEY_SYNTHETIC','enabled':True}
    model={'id':mid,'service_id':sid,'name':'Synthetic native model','kind':kind,'base_url':'https://unused.example/v1','model':'synthetic-model','enabled':True}
    monkeypatch.setattr(transport,'resolve_endpoint',lambda p:(p.base_url,['8.8.8.8'],False))
    result=client.put('/api/admin/exchange/settings',headers=csrf(client),json={'expected_revision':old['revision'],'services':[service],'providers':[model]});assert result.status_code==200,result.text
    revision=result.json()['revision'];seen=[]
    def fake(provider,suffix,payload):
        seen.append((provider,suffix,payload));text=json.dumps(output(t['slug']))
        if kind=='openai':return {'choices':[{'message':{'content':text}}],'usage':{'prompt_tokens':11,'completion_tokens':12}}
        if kind=='ollama':return {'message':{'content':text},'prompt_eval_count':11,'eval_count':12}
        if kind=='anthropic':return {'content':[{'type':'text','text':text}],'usage':{'input_tokens':11,'output_tokens':12}}
        return {'candidates':[{'content':{'parts':[{'text':text}]}}],'usageMetadata':{'promptTokenCount':11,'candidatesTokenCount':12}}
    monkeypatch.setattr(transport,'post',fake)
    try:
        data=request_data(mid,revision,t['slug']);response=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data)
        assert response.status_code==200,response.text;row=response.json()
        assert row['state']=='succeeded' and row['preview']['valid'] and row['usage_known'] and row['input_tokens']==11 and row['output_tokens']==12
        replay=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data)
        assert replay.status_code==200 and replay.json()['replayed'] and len(seen)==1
        assert seen[0][0].base_url==service['base_url'] and seen[0][0].id==uuid.UUID(mid)
        from sqlalchemy import select,func
        from app.content_models import ContentRecord
        with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(ContentRecord).where(ContentRecord.type_id==t['id']))==0
    finally:
        old['expected_revision']=revision;old.pop('revision');assert client.put('/api/admin/exchange/settings',headers=csrf(client),json=old).status_code==200
