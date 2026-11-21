"""API-level mock calls only: no external endpoint or paid provider used."""
import json,uuid
import pytest
from sqlalchemy import select,func
from test_content import client,make_type
from test_api import csrf,reset_limiter,SessionLocal
from app.exchange import transport,invocations
from app.exchange.models import AIInvocation
from app.content_models import ContentRecord


@pytest.fixture(autouse=True)
def restore_synthetic_settings():
    from app.blog_models import SiteConfig
    from app.exchange.settings import Configuration
    with SessionLocal() as db:
        old=db.scalar(select(SiteConfig).where(SiteConfig.key=='ai-writing'))
        saved=json.loads(json.dumps(old.value)) if old else Configuration().model_dump(mode='json')
    yield
    with SessionLocal() as db:
        row=db.scalar(select(SiteConfig).where(SiteConfig.key=='ai-writing'))
        if row:row.value=saved;row.revision+=1;db.commit()


def configure(c):
    old=c.get('/api/admin/exchange/settings').json();id=str(uuid.uuid4())
    data={'expected_revision':old['revision'],'providers':[{'id':id,'name':'隔离模拟','kind':'ollama','base_url':'https://model.example','model':'mock-only','enabled':False,'daily_requests':2}],'rules':old['rules']}
    saved=c.put('/api/admin/exchange/settings',headers=csrf(c),json=data);assert saved.status_code==200
    # Directly enable only this synthetic DB row. No actual DNS/paid network call.
    from app.blog_models import SiteConfig
    with SessionLocal() as db:
        row=db.scalar(select(SiteConfig).where(SiteConfig.key=='ai-writing'));value=dict(row.value);value['providers']=[{**p,'enabled':True} for p in value['providers']];row.value=value;db.commit()
    return id,saved.json()['revision']


def output(slug):
    return {'format':'life-journal.exchange','version':1,'records':[{'key':'one','type_slug':slug,'title':'模拟生成的生活片段','body':'这是一段合成验收内容。','display_date':'2026-11-05'}]}


def request_data(id,revision,slug):return {'request_key':str(uuid.uuid4()),'provider_id':id,'expected_config_revision':revision,'type_slug':slug,'materials':'全部素材为虚构','consent':True}


def test_model_output_only_creates_preview_and_same_request_never_calls_twice(client,monkeypatch):
    t=make_type(client);id,revision=configure(client);data=request_data(id,revision,t['slug']);seen=[]
    def fake(provider,suffix,payload):
        seen.append((suffix,payload));return {'message':{'content':json.dumps(output(t['slug']))},'prompt_eval_count':21,'eval_count':34}
    monkeypatch.setattr(transport,'post',fake)
    a=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data);assert a.status_code==200,a.text
    row=a.json();assert row['state']=='succeeded' and row['preview']['valid'] and row['input_tokens']==21 and row['output_tokens']==34 and row['usage_known']
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(ContentRecord).where(ContentRecord.type_id==t['id']))==0
    b=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data);assert b.status_code==200 and b.json()['replayed']
    assert len(seen)==1 and seen[0][0]=='/api/chat' and seen[0][1]['stream'] is False
    data['materials']='新输入不能重放旧请求'
    assert client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data).status_code==409
    assert len(seen)==1


def test_model_cannot_guess_media_identity_and_failed_calls_do_not_retry(client,monkeypatch):
    t=make_type(client);id,revision=configure(client);data=request_data(id,revision,t['slug']);seen=[]
    def bad(*args):
        seen.append(1);value=output(t['slug']);value['media']=[{'key':'photo','existing_id':str(uuid.uuid4())}]
        return {'message':{'content':json.dumps(value)}}
    monkeypatch.setattr(transport,'post',bad)
    result=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data);assert result.status_code==502
    retry=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data);assert retry.status_code==200 and retry.json()['state']=='failed' and retry.json()['job_id'] is None
    assert len(seen)==1


def test_cancellation_discards_result_but_does_not_claim_no_billing(client,monkeypatch):
    t=make_type(client);id,revision=configure(client);data=request_data(id,revision,t['slug'])
    def cancelled(*args):
        with SessionLocal() as db:
            row=db.scalar(select(AIInvocation).where(AIInvocation.request_key==data['request_key']))
            value=invocations.cancel(db,row.id,row.actor_id);assert value['state']=='running' and value['error_code']=='cancel_requested'
        return {'message':{'content':json.dumps(output(t['slug']))},'prompt_eval_count':11,'eval_count':12}
    monkeypatch.setattr(transport,'post',cancelled)
    result=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data);assert result.status_code==200,result.text
    row=result.json();assert row['state']=='cancelled' and row['job_id'] is None and row['usage_known'] and row['output_tokens']==12


def test_call_quota_and_explicit_consent_are_enforced(client,monkeypatch):
    t=make_type(client);id,revision=configure(client);data=request_data(id,revision,t['slug'])
    monkeypatch.setattr(transport,'post',lambda *args:{'message':{'content':json.dumps(output(t['slug']))}})
    missing={k:v for k,v in data.items() if k!='consent'}
    assert client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=missing).status_code==422
    assert client.post('/api/admin/exchange/ai/generate',json=data).status_code==403
    for i in range(2):
        data['request_key']=str(uuid.uuid4());assert client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data).status_code==200
    data['request_key']=str(uuid.uuid4());assert client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data).status_code==429


def test_openai_adapter_honors_model_output_limit_and_records_reported_usage(client,monkeypatch):
    t=make_type(client);id,revision=configure(client);data=request_data(id,revision,t['slug'])
    from app.blog_models import SiteConfig
    with SessionLocal() as db:
        row=db.scalar(select(SiteConfig).where(SiteConfig.key=='ai-writing'));value=dict(row.value)
        value['providers']=[{**p,'kind':'openai','base_url':'https://model.example/v1','key_env':'LJ_AI_KEY_MOCK'} for p in value['providers']];row.value=value;db.commit()
    def fake(provider,suffix,payload):
        assert suffix=='/chat/completions' and payload['response_format']=={'type':'json_object'} and payload['max_tokens']==2048
        return {'choices':[{'message':{'content':json.dumps(output(t['slug']))}}],'usage':{'prompt_tokens':8,'completion_tokens':13}}
    monkeypatch.setattr(transport,'post',fake)
    result=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data)
    assert result.status_code==200,result.text
    assert result.json()['input_tokens']==8 and result.json()['output_tokens']==13


def test_changed_rules_during_model_request_never_create_a_preview(client,monkeypatch):
    t=make_type(client);id,revision=configure(client);data=request_data(id,revision,t['slug'])
    from app.blog_models import SiteConfig
    def changed(*args):
        with SessionLocal() as db:
            row=db.scalar(select(SiteConfig).where(SiteConfig.key=='ai-writing'));row.revision+=1;db.commit()
        return {'message':{'content':json.dumps(output(t['slug']))}}
    monkeypatch.setattr(transport,'post',changed)
    result=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data)
    assert result.status_code==409
    with SessionLocal() as db:
        row=db.scalar(select(AIInvocation).where(AIInvocation.request_key==data['request_key']))
        assert row.state=='failed' and row.job_id is None


def test_one_time_rules_are_persisted_in_preview_without_mutating_saved_defaults(client,monkeypatch):
    t=make_type(client);id,revision=configure(client);data=request_data(id,revision,t['slug']);data['preferences']={'require_end':True}
    monkeypatch.setattr(transport,'post',lambda *args:{'message':{'content':json.dumps(output(t['slug']))}})
    result=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data)
    assert result.status_code==200,result.text
    preview=result.json()['preview'];assert preview['input']['preferences']=={'require_end':True}
    assert preview['contexts']['one']['rules']['preferences']['require_end'] is True
    assert any(i['scope'].endswith('travel.end_date') and i['level']=='warning' for i in preview['issues'])
    assert client.get('/api/admin/exchange/settings').json()['rules']['global_preferences']=={}


def test_concurrent_model_calls_are_serialized_without_duplicate_billing(client,monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    t=make_type(client);id,revision=configure(client);first=request_data(id,revision,t['slug']);second=request_data(id,revision,t['slug'])
    entered=threading.Event();release=threading.Event();seen=[]
    def delayed(*args):
        seen.append(1);entered.set()
        if not release.wait(5):raise RuntimeError('bounded synthetic provider timeout')
        return {'message':{'content':json.dumps(output(t['slug']))}}
    monkeypatch.setattr(transport,'post',delayed);headers=csrf(client)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(client.post,'/api/admin/exchange/ai/generate',headers=headers,json=first)
        try:
            assert entered.wait(3)
            blocked=client.post('/api/admin/exchange/ai/generate',headers=headers,json=second)
            assert blocked.status_code==409
            replay=client.post('/api/admin/exchange/ai/generate',headers=headers,json=first)
            assert replay.status_code==200 and replay.json()['state']=='running' and replay.json()['replayed']
        finally:release.set()
        assert pending.result(timeout=5).status_code==200
    assert len(seen)==1


def upload_photo(c):
    import io
    from PIL import Image
    photo=Image.new('RGB',(90,60),'#a7cbb8');exif=Image.Exif();exif[270]='synthetic-private-exif-note';exif[36867]='2026:10:01 12:30:00'
    b=io.BytesIO();photo.save(b,format='JPEG',exif=exif)
    response=c.post('/api/admin/archive/media',headers=csrf(c),files={'file':('synthetic-vision.jpg',b.getvalue(),'image/jpeg')})
    assert response.status_code==200,response.text
    return response.json()['id']


def test_vision_sends_only_sanitized_selected_previews_and_server_maps_photo_keys(client,monkeypatch):
    import base64,io
    from PIL import Image
    from app.blog_models import SiteConfig
    t=make_type(client);id,revision=configure(client);media=upload_photo(client);data=request_data(id,revision,t['slug']);data.update(media_ids=[media],photo_consent=True)
    with SessionLocal() as db:
        row=db.scalar(select(SiteConfig).where(SiteConfig.key=='ai-writing'));value=dict(row.value);value['providers']=[{**p,'vision':True} for p in value['providers']];row.value=value;db.commit()
    def fake(provider,suffix,payload):
        text=json.dumps(payload)
        assert media not in text and 'synthetic-private-exif-note' not in text and 'synthetic-vision.jpg' not in text
        pixels=base64.b64decode(payload['messages'][-1]['images'][0]);image=Image.open(io.BytesIO(pixels))
        assert image.format=='JPEG' and not image.getexif() and image.width<=768 and image.height<=768
        value=output(t['slug']);value['media']=[{'key':'selected-1','path':'selected-1','caption':'明确选择的照片'}]
        value['records'][0].update(body='模拟看图故事\n\n{{media:selected-1}}',cover_key='selected-1',media_keys=['selected-1'])
        return {'message':{'content':json.dumps(value)}}
    monkeypatch.setattr(transport,'post',fake)
    response=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data);assert response.status_code==200,response.text
    preview=response.json()['preview'];assert preview['valid']
    assert preview['input']['media'][0]['existing_id']==media and preview['input']['media'][0]['path'] is None
    assert media in preview['records'][0]['compiled_body']
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(ContentRecord).where(ContentRecord.type_id==t['id']))==0


def test_selected_photo_reference_does_not_send_pixels_without_separate_opt_in(client,monkeypatch):
    t=make_type(client);id,revision=configure(client);media=upload_photo(client);data=request_data(id,revision,t['slug']);data['media_ids']=[media]
    def fake(provider,suffix,payload):
        assert 'images' not in payload['messages'][-1] and 'data:image' not in json.dumps(payload)
        user=json.loads(payload['messages'][-1]['content']);assert user['selected_media']==[{'key':'selected-1','path':'selected-1'}]
        assert media not in json.dumps(payload)
        return {'message':{'content':json.dumps(output(t['slug']))}}
    monkeypatch.setattr(transport,'post',fake)
    response=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data);assert response.status_code==200,response.text


def test_nonvision_model_cannot_receive_photos_even_with_user_checkbox(client,monkeypatch):
    t=make_type(client);id,revision=configure(client);media=upload_photo(client);data=request_data(id,revision,t['slug']);data.update(media_ids=[media],photo_consent=True)
    sent=[];monkeypatch.setattr(transport,'post',lambda *args:sent.append(1))
    response=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data)
    assert response.status_code==422 and not sent


def test_expired_unknown_call_requires_explicit_abandon_and_never_applies_late_result(client,monkeypatch):
    from datetime import timedelta
    from app.models import now
    t=make_type(client);id,revision=configure(client);data=request_data(id,revision,t['slug'])
    def delayed(*args):
        with SessionLocal() as db:
            row=db.scalar(select(AIInvocation).where(AIInvocation.request_key==data['request_key']))
            response=client.post('/api/admin/exchange/ai/calls/'+row.id+'/abandon',headers=csrf(client),json={'confirmation':'确认状态未知'})
            assert response.status_code==409
            row.created_at=now()-timedelta(minutes=10);db.commit()
            assert client.post('/api/admin/exchange/ai/calls/'+row.id+'/abandon',headers=csrf(client),json={'confirmation':'skip'}).status_code==422
            response=client.post('/api/admin/exchange/ai/calls/'+row.id+'/abandon',headers=csrf(client),json={'confirmation':'确认状态未知'})
            assert response.status_code==200 and response.json()['state']=='unknown'
        return {'message':{'content':json.dumps(output(t['slug']))},'prompt_eval_count':11,'eval_count':15}
    monkeypatch.setattr(transport,'post',delayed)
    response=client.post('/api/admin/exchange/ai/generate',headers=csrf(client),json=data)
    assert response.status_code==200,response.text
    assert response.json()['state']=='unknown' and response.json()['job_id'] is None
    assert response.json()['input_tokens']==11 and response.json()['usage_known']
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(ContentRecord).where(ContentRecord.type_id==t['id']))==0


def test_every_model_configuration_and_call_route_requires_admin(client):
    from fastapi.testclient import TestClient
    from test_api import User,ph
    id=str(uuid.uuid4())
    paths=[('GET','/settings'),('PUT','/settings'),('POST','/ai/generate'),('GET','/ai/calls'),('GET','/ai/calls/'+id),('POST','/ai/calls/'+id+'/cancel'),('POST','/ai/calls/'+id+'/abandon'),('GET','/ai/requests/'+id)]
    username='synthetic-ai-reader-'+uuid.uuid4().hex;password=uuid.uuid4().hex
    with SessionLocal() as db:db.add(User(username=username,password_hash=ph.hash(password)));db.commit()
    for authenticated,expected in ((False,401),(True,403)):
        with TestClient(client.app,base_url='https://testserver') as actor:
            if authenticated:assert actor.post('/api/auth/login',headers=csrf(actor),json={'username':username,'password':password}).status_code==200
            for method,path in paths:
                response=actor.request(method,'/api/admin/exchange'+path,headers=csrf(actor),json={} if method!='GET' else None)
                assert response.status_code==expected,(method,path,response.status_code)


def test_ai_tag_candidates_use_existing_normalization_without_truncating_or_editing_body():
    from types import SimpleNamespace
    from app.exchange.invocations import response_data
    from pydantic import ValidationError
    value={'format':'life-journal.exchange','version':1,'records':[{'key':'one','type_slug':'custom','title':'合成候选','body':'# 原正文保持不变','tags':['  旅行  ','旅行','FOOD','ｆｏｏｄ']} ]}
    def response():return {'message':{'content':json.dumps(value)},'prompt_eval_count':2,'eval_count':3}
    parsed,usage,known=response_data(SimpleNamespace(kind='ollama'),response())
    assert parsed.records[0].tags==['旅行','FOOD'] and parsed.records[0].body=='# 原正文保持不变'
    assert known and usage==(2,3)
    value['records'][0]['tags']=['tag'+str(i) for i in range(11)]
    with pytest.raises(ValidationError):response_data(SimpleNamespace(kind='ollama'),response())
    value['records'][0]['tags']=['x'*41]
    with pytest.raises(ValueError,match='现有规范'):response_data(SimpleNamespace(kind='ollama'),response())


def test_full_article_prompt_uses_actual_schema_and_keeps_unknown_dates_and_defaults_private(client):
    from types import SimpleNamespace
    from test_content import field
    from app.exchange.context import context
    t=make_type(client,fields=[field('short_text',has_default=True,default_value='不应发送的默认内容')|{'name':'用户自定义字段'}])
    data=invocations.GenerateIn(request_key=uuid.uuid4(),provider_id=uuid.uuid4(),expected_config_revision=1,type_slug=t['slug'],materials='只有本人提供的事实',consent=True)
    with SessionLocal() as db:ctx=context(db,t['slug'])
    path,payload=invocations.request_payload(SimpleNamespace(kind='ollama',model='mock',max_output_tokens=512),data,ctx)
    assert path=='/api/chat' and payload['format']=='json'
    instructions,raw=payload['messages'][0]['content'].split('\n',1)
    assert '不是仅生成正文' in instructions and '展示日期不等于旅行结束日期' in instructions and '不猜测具体归属' in instructions
    assert json.loads(raw)['type']['fields'][0]['id']==t['fields'][0]['id']
    assert '不应发送的默认内容' not in json.dumps(payload,ensure_ascii=False)
    assert json.loads(payload['messages'][1]['content'])['display_date'] is None
