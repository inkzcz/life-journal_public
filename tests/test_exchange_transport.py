"""No paid/external calls: real pinned loopback server, mocked public DNS."""
import json,socket,threading,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from test_api import reset_limiter
from app.exchange.settings import Provider,Configuration,endpoint
from app.exchange.transport import resolve_endpoint,post


def provider(**kwargs):
    return Provider(id=uuid.uuid4(),name='受控本地模型',kind='ollama',base_url='http://127.0.0.1:11434',model='synthetic',**kwargs)


@pytest.mark.parametrize('url',['https://user:secret@example.com','https://example.com/?key=secret','https://example.com/#x','https://example.com/%2e%2e','https://example.com/\n','file:///tmp/file','http://example.com.:80'])
def test_endpoint_never_accepts_credentials_or_ambiguous_path(url):
    with pytest.raises(ValueError):endpoint(url)


def test_secret_keys_only_accept_dedicated_environment_references():
    with pytest.raises(ValidationError):provider(key_env='POSTGRES_PASSWORD')
    with pytest.raises(ValidationError):Provider(id=uuid.uuid4(),name='x',kind='openai',base_url='https://example.com',model='x',key_env=None)
    with pytest.raises(ValidationError):Configuration.model_validate({'api_key':'sensitive'})


@pytest.mark.parametrize('ip',['127.0.0.1','10.0.0.1','169.254.169.254','0.0.0.0','224.0.0.1','::1','::ffff:127.0.0.1'])
def test_public_dns_rejects_all_private_and_metadata_answers(monkeypatch,ip):
    p=provider().model_copy(update={'base_url':'https://model.example'})
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',(ip,443))])
    with pytest.raises(HTTPException):resolve_endpoint(p)


def test_mixed_dns_answer_cannot_hide_private_address(monkeypatch):
    p=provider().model_copy(update={'base_url':'https://model.example'})
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('8.8.8.8',443)),(2,1,6,'',('10.0.0.1',443))])
    with pytest.raises(HTTPException):resolve_endpoint(p)


def test_real_local_http_request_requires_exact_server_opt_in_and_never_follows_redirect(monkeypatch):
    seen=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_POST(self):
            raw=self.rfile.read(int(self.headers['Content-Length']));seen.append((self.path,json.loads(raw),self.headers['Host']))
            if self.path.endswith('/redirect'):
                self.send_response(302);self.send_header('Location','http://169.254.169.254/latest/meta-data');self.end_headers();return
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"message":{"content":"synthetic"}}')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_port)
    p=provider().model_copy(update={'base_url':base})
    monkeypatch.setenv('NO_PROXY','127.0.0.1')
    try:
        monkeypatch.delenv('LJ_AI_OLLAMA_ALLOWED_ORIGINS',raising=False)
        with pytest.raises(HTTPException):post(p,'/api/chat',{})
        assert not seen
        monkeypatch.setenv('LJ_AI_OLLAMA_ALLOWED_ORIGINS',base)
        assert post(p,'/api/chat',{'stream':False})['message']['content']=='synthetic'
        with pytest.raises(HTTPException) as error:post(p,'/redirect',{})
        assert error.value.status_code==502 and '重定向' in error.value.detail
        assert len(seen)==2 and seen[0][2]==base.removeprefix('http://')
    finally:server.shutdown();server.server_close();thread.join(timeout=3)


def test_request_pins_verified_ip_and_preserves_tls_sni_without_second_dns(monkeypatch):
    from app.exchange import transport
    from contextlib import contextmanager
    p=provider().model_copy(update={'base_url':'https://model.example/v1'})
    queries=[];seen=[]
    def dns(*args,**kwargs):
        queries.append(args[0]);return [(2,1,6,'',('8.8.8.8',443))]
    monkeypatch.setattr(socket,'getaddrinfo',dns)
    class Response:
        status=200
        def iter_stream(self):yield b'{"ok":true}'
    class Pool:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        @contextmanager
        def stream(self,method,url,**kwargs):
            seen.append((method,url,kwargs));yield Response()
    monkeypatch.setattr(transport,'_pool',lambda parsed:Pool())
    assert post(p,'/chat/completions',{})=={'ok':True}
    assert queries==['model.example']
    assert seen[0][1]=='https://8.8.8.8/v1/chat/completions'
    assert seen[0][2]['headers']['Host']=='model.example'
    assert seen[0][2]['extensions']['sni_hostname']=='model.example'


def test_explicit_local_exception_still_rejects_link_local_metadata(monkeypatch):
    p=provider().model_copy(update={'base_url':'http://local-model:11434'})
    monkeypatch.setenv('LJ_AI_OLLAMA_ALLOWED_ORIGINS',p.base_url)
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('169.254.169.254',11434))])
    with pytest.raises(HTTPException):resolve_endpoint(p)


def test_local_dns_rebinding_cannot_switch_to_another_approved_origin_ip(monkeypatch):
    p=provider().model_copy(update={'base_url':'http://local-model:11434'})
    monkeypatch.setenv('LJ_AI_OLLAMA_ALLOWED_ORIGINS','http://local-model:11434,http://second-model:11434')
    monkeypatch.setenv('LJ_AI_OLLAMA_ORIGIN_IPS',json.dumps({'http://local-model:11434':['10.0.0.1'],'http://second-model:11434':['10.0.0.2']}))
    current=['10.0.0.1']
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',(current[0],11434))])
    assert resolve_endpoint(p)[1]==['10.0.0.1']
    current[0]='10.0.0.2'
    with pytest.raises(HTTPException):resolve_endpoint(p)


def test_local_hostname_is_not_trusted_without_server_ip_binding(monkeypatch):
    p=provider().model_copy(update={'base_url':'http://local-model:11434'})
    monkeypatch.setenv('LJ_AI_OLLAMA_ALLOWED_ORIGINS',p.base_url)
    monkeypatch.delenv('LJ_AI_OLLAMA_ORIGIN_IPS',raising=False)
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('10.0.0.1',11434))])
    with pytest.raises(HTTPException):resolve_endpoint(p)


def test_explicit_local_https_origin_cannot_rebind_to_public_and_drop_its_ip_binding(monkeypatch):
    p=provider().model_copy(update={'base_url':'https://local-model:11434'})
    monkeypatch.setenv('LJ_AI_OLLAMA_ALLOWED_ORIGINS',p.base_url)
    monkeypatch.setenv('LJ_AI_OLLAMA_ORIGIN_IPS',json.dumps({p.base_url:['10.0.0.1']}))
    current=['10.0.0.1']
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',(current[0],11434))])
    assert resolve_endpoint(p)[1]==['10.0.0.1']
    current[0]='93.184.216.34'
    with pytest.raises(HTTPException):resolve_endpoint(p)
