"""Synthetic protocol fixtures only: never credentials or external API calls."""
from contextlib import contextmanager
import json,socket,uuid
import pytest
from fastapi import HTTPException
from app.exchange import adapters,transport
from app.exchange.settings import Configuration,Provider,Service


def profile(kind,**changes):
    return Provider(id=uuid.uuid4(),name='Synthetic',kind=kind,base_url='https://synthetic.example/v1',model='synthetic-model',key_env='LJ_AI_KEY_SYNTHETIC',vision=True,**changes)


@pytest.mark.parametrize('kind,path',[('openai','/chat/completions'),('ollama','/api/chat'),('anthropic','/messages'),('gemini','/models/synthetic-model:generateContent')])
def test_protocol_requests_and_image_shapes(kind,path):
    p=profile(kind);suffix,payload=adapters.request(p,'system','private text',['YWJj'])
    assert suffix==path and 'private text' in json.dumps(payload)
    assert payload.get('stream') in (None,False)
    if kind=='openai':
        assert payload['messages'][0]=={'role':'system','content':'system'}
        assert payload['messages'][1]['content'][1]['image_url']['url']=='data:image/jpeg;base64,YWJj'
        assert payload['max_tokens']==2048
    elif kind=='ollama':assert payload['messages'][1]['images']==['YWJj'] and payload['options']['num_predict']==2048
    elif kind=='anthropic':assert payload['system']=='system' and payload['messages'][0]['content'][1]['source']=={'type':'base64','media_type':'image/jpeg','data':'YWJj'}
    else:assert payload['contents'][0]['parts'][1]['inlineData']=={'mimeType':'image/jpeg','data':'YWJj'}


@pytest.mark.parametrize('kind,value',[('openai',{'choices':[{'message':{'content':'{"test":1}'}}],'usage':{'prompt_tokens':3,'completion_tokens':4}}),('ollama',{'message':{'content':'{"test":1}'},'prompt_eval_count':3,'eval_count':4}),('anthropic',{'content':[{'type':'thinking','thinking':'hidden'},{'type':'text','text':'{"test":1}'}],'usage':{'input_tokens':3,'output_tokens':4}}),('gemini',{'candidates':[{'content':{'parts':[{'text':'hidden','thought':True},{'text':'{"test":1}'}]}}],'usageMetadata':{'promptTokenCount':3,'candidatesTokenCount':4}})])
def test_protocol_text_usage_and_no_hidden_thoughts(kind,value):
    assert adapters.response(profile(kind),value)==('{"test":1}',(3,4),True)
    value.pop('usage',None);value.pop('usageMetadata',None);value.pop('eval_count',None)
    assert adapters.response(profile(kind),value)[2] is False


@pytest.mark.parametrize('kind',['openai','ollama','anthropic','gemini'])
def test_reasoning_never_forces_json_or_temperature(kind):
    _,payload=adapters.request(profile(kind,reasoning=True),'s','u')
    assert not any(key in payload for key in ('temperature','response_format','format'))
    assert 'responseMimeType' not in payload.get('generationConfig',{})
    if kind=='openai':assert 'max_completion_tokens' in payload and 'max_tokens' not in payload
    with pytest.raises(HTTPException):adapters.request(profile(kind).model_copy(update={'vision':False}),'s','u',['YWJj'])
    with pytest.raises(HTTPException):adapters.request(profile(kind,text=False),'s','u')


@pytest.mark.parametrize('model',['../secret','models/../../secret','x?key=secret','x#y','x/y','x:generateContent'])
def test_gemini_path_cannot_be_injected(model):
    with pytest.raises(HTTPException):adapters.request(profile('gemini').model_copy(update={'model':model}),'s','u')


@pytest.mark.parametrize('kind,value,expected',[('openai',{'data':[{'id':'one'}]},'one'),('ollama',{'models':[{'name':'one:tag'}]},'one:tag'),('anthropic',{'data':[{'id':'one','display_name':'Name'}]},'one'),('gemini',{'models':[{'name':'models/embedding','supportedGenerationMethods':['embedContent']},{'name':'models/one','supportedGenerationMethods':['generateContent']}]},'one')])
def test_model_listing_does_not_invent_capabilities(kind,value,expected):
    items=adapters.models(profile(kind),value)
    assert len(items)==1 and items[0]['id']==expected and set(items[0])=={'id','name'}
    with pytest.raises(ValueError):adapters.models(profile(kind),{'data':'invalid','models':'invalid'})


def test_service_configuration_is_additive_and_retains_legacy_identity_and_references():
    old=profile('openai');old_json=old.model_dump(mode='json');old_config=Configuration(default_provider=old.id,providers=[old])
    assert old_config.profiles()[0].model_dump(mode='json')==old_json
    s=Service(id=uuid.uuid4(),name='Shared',kind='anthropic',base_url='https://new.example/v1',key_env='LJ_AI_KEY_SHARED',enabled=False)
    model=old.model_copy(update={'service_id':s.id,'enabled':True})
    config=Configuration(providers=[model],services=[s],task_defaults={'summary':old.id})
    effective=config.profiles()[0]
    assert effective.id==old.id and effective.kind=='anthropic' and effective.key_env=='LJ_AI_KEY_SHARED' and not effective.enabled
    assert config.providers[0].key_env==old.key_env # original metadata retained, never plaintext
    # Removing a model preserves the affected task identity for explicit repair.
    assert Configuration(task_defaults={'summary':old.id}).task_defaults['summary']==old.id


@pytest.mark.parametrize('kind,header',[('openai','Authorization'),('ollama','Authorization'),('anthropic','x-api-key'),('gemini','x-goog-api-key')])
def test_get_model_list_uses_same_pinned_transport_and_protocol_auth(monkeypatch,kind,header):
    queries=[];seen=[]
    monkeypatch.setenv('LJ_AI_KEY_SYNTHETIC','SYNTHETIC-NOT-A-REAL-KEY')
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:queries.append(a[0]) or [(2,1,6,'',('8.8.8.8',443))])
    class Response:
        status=200
        def iter_stream(self):yield b'{"data":[]}'
    class Pool:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        @contextmanager
        def stream(self,method,url,**kwargs):seen.append((method,url,kwargs));yield Response()
    monkeypatch.setattr(transport,'_pool',lambda parsed:Pool())
    assert transport.get(profile(kind),'/models')=={'data':[]}
    assert queries==['synthetic.example'] and seen[0][0]=='GET' and seen[0][1]=='https://8.8.8.8/v1/models'
    headers=seen[0][2]['headers'];assert header in headers
    if kind in {'anthropic','gemini'}:assert 'Authorization' not in headers
    if kind=='anthropic':assert headers['anthropic-version']=='2023-06-01'


@pytest.mark.parametrize('status,expected',[(401,502),(403,502),(404,502),(429,429),(500,502),(302,502)])
def test_provider_errors_never_expose_server_body_or_keys(monkeypatch,status,expected):
    monkeypatch.setenv('LJ_AI_KEY_SYNTHETIC','SYNTHETIC-NOT-A-REAL-KEY')
    monkeypatch.setattr(transport,'resolve_endpoint',lambda p:(p.base_url,['8.8.8.8'],False))
    class Response:
        def iter_stream(self):raise AssertionError('error bodies must not be read')
    Response.status=status
    class Pool:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        @contextmanager
        def stream(self,*a,**k):yield Response()
    monkeypatch.setattr(transport,'_pool',lambda parsed:Pool())
    with pytest.raises(HTTPException) as error:transport.post(profile('gemini'),'/models/synthetic:generateContent',{})
    assert error.value.status_code==expected and 'SYNTHETIC' not in error.value.detail


@pytest.mark.parametrize('mode',['oversize','invalid','timeout'])
def test_transport_response_caps_invalid_json_and_timeout(monkeypatch,mode):
    monkeypatch.setenv('LJ_AI_KEY_SYNTHETIC','SYNTHETIC-NOT-A-REAL-KEY')
    monkeypatch.setattr(transport,'resolve_endpoint',lambda p:(p.base_url,['8.8.8.8'],False))
    class Response:
        status=200
        def iter_stream(self):
            if mode=='timeout':raise TimeoutError('secret server error')
            yield b'x'*(transport.MAX_RESPONSE+1) if mode=='oversize' else b'<html>secret</html>'
    class Pool:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        @contextmanager
        def stream(self,*a,**k):yield Response()
    monkeypatch.setattr(transport,'_pool',lambda parsed:Pool())
    with pytest.raises(HTTPException) as error:transport.get(profile('anthropic'),'/models')
    assert error.value.status_code==(504 if mode=='timeout' else 502) and 'secret' not in error.value.detail


def test_openai_reasoning_token_and_instruction_overrides():
    _,payload=adapters.request(profile('openai',reasoning=True,token_parameter='max_tokens',system_role='developer'),'s','u')
    assert payload['messages'][0]['role']=='developer' and payload['max_tokens']==2048 and 'max_completion_tokens' not in payload
    _,payload=adapters.request(profile('openai',token_parameter='omit'),'s','u')
    assert 'max_tokens' not in payload and 'max_completion_tokens' not in payload


def test_gemini_usage_includes_reported_billable_thought_tokens():
    value={'candidates':[{'content':{'parts':[{'text':'result'}]}}],'usageMetadata':{'promptTokenCount':3,'candidatesTokenCount':4,'thoughtsTokenCount':9}}
    assert adapters.response(profile('gemini'),value)==('result',(3,13),True)
