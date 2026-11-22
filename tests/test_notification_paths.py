"""Synthetic URLs only; no provider credentials or network notification sends."""
from urllib.parse import parse_qs, unquote, urlsplit
import pytest
from test_api import reset_limiter
from app.calendar.transport import DeliveryError, VARIABLES, get, render, template


@pytest.mark.parametrize('field',sorted(VARIABLES))
@pytest.mark.parametrize('value',['中文与 空格','/../../?admin=1#片段%+&=','..','.','https://169.254.169.254/','第一行\n第二行','%2F%3F%23','🎬 café'])
def test_every_path_variable_is_one_data_segment_with_fixed_origin(field,value):
    pattern='https://wxpusher.zjiecode.com/api/send/message/SPT_SYNTHETIC_ONLY/{'+field+'}?copy={'+field+'}'
    result=render(pattern,{field:value})
    original,parsed=urlsplit(pattern),urlsplit(result)
    assert (parsed.scheme,parsed.netloc)==(original.scheme,original.netloc)
    assert parsed.fragment=='' and parsed.path.count('/')==original.path.count('/')
    assert unquote(parsed.path.rsplit('/',1)[1])==value
    assert parse_qs(parsed.query)=={'copy':[value]}
    assert not any(segment in ('.','..') for segment in parsed.path.split('/'))


def test_mixed_path_and_query_templates_keep_static_escapes_and_duplicate_parameters():
    value='中文 /? # % +'
    result=render('https://notify.example.invalid:8443/already%2Fescaped/{title}/prefix-{name}?content={content}&x=1&x=2&empty=',
                  {'title':value,'name':'合成.姓名','content':value})
    parsed=urlsplit(result)
    assert parsed.netloc=='notify.example.invalid:8443'
    assert parsed.path.startswith('/already%2Fescaped/')
    assert unquote(parsed.path.split('/')[2])==value
    assert unquote(parsed.path.split('/')[3])=='prefix-合成.姓名'
    assert parse_qs(parsed.query,keep_blank_values=True)=={'content':[value],'x':['1','2'],'empty':['']}
    assert render('https://notify.example.invalid/static%7Bcontent%7D',{'content':'ignored'}).endswith('/static%7Bcontent%7D')


@pytest.mark.parametrize('pattern',[
    'https://{name}.example.invalid/send','{title}://example.invalid/send',
    'https://example.invalid:{days_left}/send','https://{name}:x@example.invalid/send',
    'https://user:{content}@example.invalid/send','https://example.invalid/{unknown}',
    'https://example.invalid/{name.__class__}','https://example.invalid/{name[0]}',
    'https://example.invalid/{name!r}','https://example.invalid/{name:>10}',
    'https://example.invalid/{','https://example.invalid/}','https://example.invalid/{{name}}',
    'https://example.invalid/send?{name}=x','https://example.invalid/send#{content}',
])
def test_unsafe_template_positions_and_format_operations_are_rejected_without_values(pattern):
    with pytest.raises(ValueError) as caught:template(pattern)
    assert pattern not in str(caught.value)


def test_encoding_limits_and_malformed_unicode_have_safe_errors():
    with pytest.raises(DeliveryError,match='url_too_large'):
        render('https://notify.example.invalid/{content}',{'content':'中'*2000})
    with pytest.raises(DeliveryError,match='invalid_url_data'):
        render('https://notify.example.invalid/{content}',{'content':'\ud800'})
    with pytest.raises(ValueError):template('https://notify.example.invalid/'+'a'*4000)
    with pytest.raises(DeliveryError,match='invalid_path_data'):
        render('https://notify.example.invalid/.{content}.',{'content':''})


def test_rendered_private_target_still_goes_through_ssrf_validation(monkeypatch):
    monkeypatch.setattr('socket.getaddrinfo',lambda *a,**kw:[(2,1,6,'',('169.254.169.254',443))])
    with pytest.raises(DeliveryError,match='ssrf_blocked'):
        get(render('https://notify.example.invalid/{content}',{'content':'https://example.org/'}))


def test_actual_pinned_http_request_retains_encoded_path_data_and_refuses_redirects(monkeypatch):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    seen=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            seen.append(self.path)
            self.send_response(302 if self.path.startswith('/redirect') else 200)
            if self.path.startswith('/redirect'):self.send_header('Location','http://169.254.169.254/never')
            self.end_headers();self.wfile.write(b'Synthetic response')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    origin='http://127.0.0.1:'+str(server.server_port)
    monkeypatch.setenv('LJ_NOTIFY_INTERNAL_ORIGIN_IPS',json.dumps({origin:['127.0.0.1']}))
    try:
        value='中文 / ? # % +\n..'
        assert get(render(origin+'/api/send/message/SPT_SYNTHETIC_ONLY/{content}',{'content':value}))==200
        assert unquote(seen[0].rsplit('/',1)[1])==value
        assert seen[0].count('/')==5
        with pytest.raises(DeliveryError,match='redirect_refused'):get(origin+'/redirect/{content}'.replace('{content}','synthetic'))
        assert len(seen)==2
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
    assert not thread.is_alive()
