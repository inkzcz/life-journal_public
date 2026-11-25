"""Synthetic templates and fake transport only; never a real notification token."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import json
from urllib.parse import parse_qs,urlsplit
import pytest
from app.calendar.request_templates import build,preview,validate
from app.calendar.transport import render,DeliveryError,deliver

V={'title':'合成标题','content':'换行\n"引号" & 中文','name':'合成姓名','date':'2030-01-01','days_left':3,'years':1,'calendar_type':'solar'}

def cfg(**kw):return {'url_template':'https://example.invalid/notify','method':'POST','body_format':'json','body_template':'{}',**kw}

@pytest.mark.parametrize('body',[
    {'title':'{title}','content':'{content}'},
    {'msgtype':'text','text':{'content':'{name}还有{days_left}天'}},
    {'appToken':'synthetic-value','content':'{content}','uids':['synthetic-uid'],'contentType':1},
    [None,False,17,{'markdown':'## {title}\n\n{content}'}],
])
def test_nested_json_is_parsed_before_substitution_and_data_stays_data(body):
    request=build(cfg(body_template=json.dumps(body,ensure_ascii=False)),V)
    result=json.loads(request['body'])
    assert request['headers']['Content-Type']=='application/json'
    if isinstance(body,dict) and 'content' in body:assert result['content']==V['content']
    if isinstance(body,list):assert result[:3]==[None,False,17]

@pytest.mark.parametrize('value',['{}','{"title":"{title}","text":"{content}"}','{content}','{{literal}}'])
def test_complex_get_query_is_encoded_once(value):
    result=render('https://example.invalid/?content='+value,V)
    parsed=parse_qs(urlsplit(result).query,keep_blank_values=True)['content'][0]
    if value=='{}':assert parsed=='{}'
    elif value.startswith('{"'):assert json.loads(parsed)=={'title':V['title'],'text':V['content']}
    elif value=='{content}':assert parsed==V['content']
    else:assert parsed=='{literal}'

@pytest.mark.parametrize('fmt,body',[('form','content={"text":"{content}"}'),('text','标题：{title}\n{content}')])
def test_form_and_plain_text_preserve_unicode(fmt,body):
    result=build(cfg(body_format=fmt,body_template=body),V)
    if fmt=='form':assert json.loads(parse_qs(result['body'].decode())['content'][0])['text']==V['content']
    else:assert result['body'].decode()=='标题：'+V['title']+'\n'+V['content']

@pytest.mark.parametrize('name',['Host','Content-Length','Transfer-Encoding','Connection','TE','Content-Type','Proxy-Authorization','X\r\nInjected'])
def test_dangerous_headers_are_rejected(name):
    with pytest.raises(ValueError):build(cfg(headers=[{'name':name,'value':'synthetic'}]),V)

@pytest.mark.parametrize('body',['{"value":"{unknown}"}','{"{name}":1}','{"value":NaN}','{"value":"{name.__class__}"}'])
def test_unknown_variables_and_nonstandard_json_fail_closed(body):
    with pytest.raises(ValueError):build(cfg(body_template=body),V)


def test_credential_preview_never_returns_original_values_and_never_sends():
    secret='synthetic-preview-credential'
    c=cfg(url_template='https://example.invalid/'+secret+'?token='+secret,headers=[{'name':'Authorization','value':'Bearer '+secret}],body_template=json.dumps({'appToken':secret,'content':'{content}'}))
    result=preview(c,V)
    assert secret not in json.dumps(result) and V['content'] not in json.dumps(result)
    assert result['external_request_sent'] is False and result['template_result']=='valid'


def test_header_injection_from_variable_and_size_limits_are_checked_after_render():
    with pytest.raises(ValueError):build(cfg(headers=[{'name':'Authorization','value':'{content}'}]),V)
    with pytest.raises(ValueError):build(cfg(body_format='text',body_template='{content}'),{**V,'content':'中'*30000})
    with pytest.raises(ValueError):build(cfg(headers=[{'name':'X-Synthetic','value':'ok'}]*21),V)


def test_legacy_get_injection_and_post_transport_have_separate_safe_contracts():
    calls=[]
    assert deliver(cfg(method='GET'),V,legacy_get=lambda url:calls.append(url) or 200)==200
    assert calls==['https://example.invalid/notify']
    def sender(method,url,headers,body):
        assert method=='POST' and json.loads(body)=={};return 204
    assert deliver(cfg(),V,request_sender=sender)==204


@pytest.mark.parametrize('method,status,expected,uncertain,retryable',[
    ('POST',204,'ok',False,False),('POST',500,'http_error',True,False),
    ('POST',429,'http_error',False,False),('POST',302,'redirect_refused',True,False),
    ('GET',204,'http_error',False,False),('GET',503,'http_error',False,True),
])
def test_pinned_http_request_keeps_host_tls_identity_and_never_follows_redirects(monkeypatch,method,status,expected,uncertain,retryable):
    from app.calendar import transport
    calls=[]
    monkeypatch.setattr(transport.socket,'getaddrinfo',lambda *a,**k:[(None,None,None,None,('8.8.8.8',443))])
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_stream(self):yield b'synthetic-response'
    Response.status=status
    class Pool:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def stream(self,*args,**kwargs):calls.append((args,kwargs));return Response()
    monkeypatch.setattr(transport,'_pool',lambda p:Pool())
    if expected=='ok':assert transport.request(method,'https://example.invalid/path?x=1',{'Authorization':'synthetic-auth'},b'{}')==status
    else:
        with pytest.raises(DeliveryError) as caught:transport.request(method,'https://example.invalid/path?x=1',{},b'{}')
        assert caught.value.code==expected and caught.value.uncertain is uncertain and caught.value.retryable is retryable
    assert len(calls)==1
    args,options=calls[0]
    assert args==(method,'https://8.8.8.8/path?x=1')
    assert (b'Host',b'example.invalid') in options['headers']
    assert options['extensions']['sni_hostname']=='example.invalid'


@pytest.mark.parametrize('exception,uncertain,retryable',[('ConnectTimeout',False,True),('ReadTimeout',True,False),('WriteTimeout',True,False)])
def test_post_request_phase_distinguishes_safe_failure_and_unknown_outcome(monkeypatch,exception,uncertain,retryable):
    from app.calendar import transport
    import httpcore
    monkeypatch.setattr(transport.socket,'getaddrinfo',lambda *a,**k:[(None,None,None,None,('8.8.8.8',443))])
    class Pool:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def stream(self,*args,**kwargs):raise getattr(httpcore,exception)('synthetic-sensitive-message')
    monkeypatch.setattr(transport,'_pool',lambda p:Pool())
    with pytest.raises(DeliveryError) as caught:transport.request('POST','https://example.invalid/',{},b'{}')
    assert caught.value.uncertain is uncertain and caught.value.retryable is retryable
    assert 'synthetic-sensitive-message' not in str(caught.value)


def test_legacy_escaped_json_structure_gets_safe_structured_string_substitution():
    value='{{"content":"{content}","literal":"{{title}}"}}'
    parsed=parse_qs(urlsplit(render('https://example.invalid/?content='+value,V)).query)['content'][0]
    assert json.loads(parsed)=={'content':V['content'],'literal':'{title}'}


def test_get_and_form_combine_multiple_variables_at_start_of_value():
    template='content={name}还有{days_left}天'
    value=parse_qs(urlsplit(render('https://example.invalid/?'+template,V)).query)['content'][0]
    assert value==V['name']+'还有3天'
    request=build(cfg(body_format='form',body_template=template),V)
    assert parse_qs(request['body'].decode())['content']==[value]
