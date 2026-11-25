"""Pinned GET, separately encoded path/query data, no redirects, safe outcomes."""
import ipaddress,json,os,socket,time
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode,quote
from string import Formatter
from .request_templates import query_value
import httpcore
from ..exchange.transport import _pool
VARIABLES={'title','content','name','date','days_left','years','calendar_type'}

class DeliveryError(Exception):
    def __init__(self,code,*,uncertain=False,retryable=False,status=None):
        super().__init__(code);self.code=code;self.uncertain=uncertain;self.retryable=retryable;self.status=status

def _tokens(value,*,path=False):
    parts=list(Formatter().parse(value))
    for literal,field,spec,conv in parts:
        if field is not None and (field not in VARIABLES or spec or conv):raise ValueError()
        # Escaped braces were historically supported in query values. Paths did
        # not support braces: require explicit known variables, not new literals.
        if path and ('{' in literal or '}' in literal):raise ValueError()
    return parts

def template(value):
    try:
        p=urlsplit(value)
        if not value or value!=value.lstrip() or len(value)>4000 or any(ord(c)<32 or ord(c)==127 for c in value):raise ValueError()
        if p.scheme not in ('https','http') or not p.hostname or p.username is not None or p.password is not None or p.fragment:raise ValueError()
        if p.port is not None and not 1<=p.port<=65535:raise ValueError()
        if '{' in p.netloc or '}' in p.netloc:raise ValueError()
        if ' ' in p.path or ' ' in p.netloc:raise ValueError()
        _tokens(p.path,path=True)
        host=p.hostname.encode('idna').decode('ascii')
        if host.endswith('.') or '%' in host:raise ValueError()
        for key,val in parse_qsl(p.query,keep_blank_values=True):
            if '{' in key or '}' in key:raise ValueError()
            query_value(val,{key:'' for key in VARIABLES})
        return value
    except (ValueError,UnicodeError):raise ValueError('通知模板只允许HTTP(S)，变量只能位于路径或查询参数值中，不允许凭据或片段') from None

def render(value,variables):
    template(value);p=urlsplit(value)
    values={key:str(variables.get(key,'')) for key in VARIABLES}
    try:
        # quote() always leaves unreserved dots alone. Encode variable dots too,
        # so a value of '.'/'..' cannot become a client-normalized path segment.
        path=''.join(literal+(quote(values[field],safe='',encoding='utf-8').replace('.','%2E') if field is not None else '')
                     for literal,field,_,_ in _tokens(p.path,path=True))
        if any(segment in ('.','..') for segment in path.split('/')) and path!=p.path:
            raise DeliveryError('invalid_path_data')
        query=urlencode([(k,query_value(v,values)) for k,v in parse_qsl(p.query,keep_blank_values=True)])
        result=urlunsplit((p.scheme,p.netloc,path,query,''))
    except UnicodeError:raise DeliveryError('invalid_url_data') from None
    if urlsplit(result)[:2]!=(p.scheme,p.netloc):raise DeliveryError('invalid_url_data')
    if len(result)>16000:raise DeliveryError('url_too_large')
    return result

def resolve(p):
    try:
        addresses={str(ipaddress.ip_address(r[4][0])) for r in socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM)}
    except (OSError,ValueError):raise DeliveryError('dns_failed',retryable=True) from None
    if not 1<=len(addresses)<=16:raise DeliveryError('invalid_dns')
    origin=p.scheme+'://'+p.netloc
    try:
        raw=os.environ.get('LJ_NOTIFY_INTERNAL_ORIGIN_IPS','{}')
        if len(raw)>20000:raise ValueError()
        allow=json.loads(raw)
        if not isinstance(allow,dict) or len(allow)>32:raise ValueError()
        approved={str(ipaddress.ip_address(v)) for v in allow.get(origin,[])}
    except (ValueError,TypeError):raise DeliveryError('invalid_internal_allowlist') from None
    local=bool(approved) and addresses<=approved
    if p.scheme!='https' and not local:raise DeliveryError('https_required')
    for raw in addresses:
        ip=ipaddress.ip_address(raw)
        if ip.is_unspecified or ip.is_multicast or ip.is_link_local or getattr(ip,'ipv4_mapped',None) or raw in ('100.100.100.200','fd00:ec2::254') or ip.is_reserved and not (local and ip.is_loopback) or not local and not ip.is_global or local and ip.is_global:
            raise DeliveryError('ssrf_blocked')
    return sorted(addresses)[0]

def get(url):
    p=urlsplit(url);ip=resolve(p);host='['+ip+']' if ':' in ip else ip
    target=urlunsplit((p.scheme,host+(':'+str(p.port) if p.port else ''),p.path or '/',p.query,''))
    deadline=time.monotonic()+10
    try:
        with _pool(p) as pool:
            with pool.stream('GET',target,headers={'Host':p.netloc,'Accept-Encoding':'identity'},extensions={'sni_hostname':p.hostname,'timeout':{'connect':5,'read':5,'write':5,'pool':1}}) as response:
                status=response.status
                if 300<=status<400:raise DeliveryError('redirect_refused',status=status)
                if status!=200:raise DeliveryError('http_error',retryable=status==429 or status>=500,status=status)
                size=0
                for chunk in response.iter_stream():
                    size+=len(chunk)
                    if size>65536:raise DeliveryError('response_too_large',uncertain=True,status=status)
                    if time.monotonic()>deadline:raise DeliveryError('response_timeout',uncertain=True,status=status)
                return status
    except DeliveryError:raise
    except (httpcore.ConnectTimeout,httpcore.ConnectError):raise DeliveryError('connect_failed',retryable=True) from None
    except Exception:raise DeliveryError('delivery_unknown',uncertain=True) from None


def request(method,url,headers=None,body=b''):
    """POST/advanced GET uses the same pinned resolver and TLS host identity."""
    if method not in ('GET','POST') or len(body)>65536:raise DeliveryError('invalid_request')
    p=urlsplit(url);ip=resolve(p);host='['+ip+']' if ':' in ip else ip
    target=urlunsplit((p.scheme,host+(':'+str(p.port) if p.port else ''),p.path or '/',p.query,''))
    outgoing=[(b'Host',p.netloc.encode('idna')),(b'Accept-Encoding',b'identity')]
    outgoing.extend((k.encode('ascii'),v.encode('utf-8')) for k,v in (headers or {}).items())
    deadline=time.monotonic()+10
    try:
        with _pool(p) as pool:
            with pool.stream(method,target,headers=outgoing,content=body,extensions={'sni_hostname':p.hostname,'timeout':{'connect':5,'read':5,'write':5,'pool':1}}) as response:
                status=response.status
                if 300<=status<400:raise DeliveryError('redirect_refused',status=status,uncertain=method=='POST')
                if not (status==200 if method=='GET' else 200<=status<300):
                    raise DeliveryError('http_error',status=status,uncertain=method=='POST' and status>=500,retryable=method=='GET' and (status==429 or status>=500))
                size=0
                for chunk in response.iter_stream():
                    size+=len(chunk)
                    if size>65536:raise DeliveryError('response_too_large',uncertain=True,status=status)
                    if time.monotonic()>deadline:raise DeliveryError('response_timeout',uncertain=True,status=status)
                return status
    except DeliveryError:raise
    except (httpcore.ConnectTimeout,httpcore.ConnectError):raise DeliveryError('connect_failed',retryable=True) from None
    except Exception:raise DeliveryError('delivery_unknown',uncertain=True) from None


def deliver(config,variables,*,legacy_get=None,request_sender=None):
    from .request_templates import build
    try:prepared=build(config,variables)
    except (ValueError,TypeError,RecursionError,UnicodeError):raise DeliveryError('invalid_request') from None
    if prepared['method']=='GET' and not prepared['headers']:
        return (legacy_get or get)(prepared['url'])
    return (request_sender or request)(prepared['method'],prepared['url'],prepared['headers'],prepared['body'])
