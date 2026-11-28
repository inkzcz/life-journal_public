"""Bounded, pinned, no-redirect transport. No provider response/body is logged."""
import ipaddress,json,os,socket,ssl,time
from urllib.parse import urlsplit,urlunsplit,unquote
from urllib.request import getproxies,proxy_bypass
import httpcore
from fastapi import HTTPException

MAX_RESPONSE=2*1024*1024
MAX_REQUEST=1024*1024


def origin(value):
    p=urlsplit(value)
    return p.scheme+'://'+p.netloc


def resolve_endpoint(provider):
    from .settings import endpoint
    base=endpoint(provider.base_url);parsed=urlsplit(base)
    allowed=set()
    for item in os.environ.get('LJ_AI_OLLAMA_ALLOWED_ORIGINS','').split(','):
        if item.strip():
            try:allowed.add(origin(endpoint(item.strip())))
            except ValueError:raise HTTPException(503,'本地模型服务端允许名单配置无效') from None
    local=provider.kind=='ollama' and origin(base) in allowed
    if parsed.scheme!='https' and not local:raise HTTPException(422,'模型端点需要HTTPS；本地Ollama须由服务端明确允许该Origin')
    try:
        addresses={str(ipaddress.ip_address(row[4][0])) for row in socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=='https' else 80),type=socket.SOCK_STREAM)}
    except (OSError,ValueError):raise HTTPException(422,'模型端点DNS解析失败') from None
    if not addresses or len(addresses)>16:raise HTTPException(422,'模型端点地址数量无效')
    if local:
        try:
            literal=str(ipaddress.ip_address(parsed.hostname))
        except ValueError:literal=None
        approved={literal} if literal else set()
        if not literal:
            try:
                from .parsers import json_data
                raw=os.environ.get('LJ_AI_OLLAMA_ORIGIN_IPS','{}')
                if len(raw)>20000:raise ValueError()
                bindings=json_data(raw.encode())
                if not isinstance(bindings,dict) or len(bindings)>32:raise ValueError()
                for key,values in bindings.items():
                    canonical=endpoint(key)
                    if urlsplit(canonical).path or not isinstance(values,list) or not 1<=len(values)<=16:raise ValueError()
                    ips={str(ipaddress.ip_address(ip)) for ip in values}
                    if origin(canonical)==origin(base):approved=ips
            except (ValueError,TypeError,UnicodeError):raise HTTPException(503,'本地模型按Origin绑定的授权IP配置无效') from None
        if not addresses<=approved:raise HTTPException(422,'本地模型DNS地址没有全部绑定到服务端授权IP，请使用允许的固定IP或显式配置允许IP')
        if any(ipaddress.ip_address(raw).is_global for raw in addresses):raise HTTPException(422,'本地例外不能混入公网地址')
    if parsed.scheme!='https' and not local:raise HTTPException(422,'公网模型端点必须使用HTTPS')
    for raw in addresses:
        address=ipaddress.ip_address(raw)
        # IPv4-mapped IPv6, metadata, unspecified, multicast and link-local
        # addresses remain forbidden even for the explicit local exception.
        if (raw in {'100.100.100.200','fd00:ec2::254'} or getattr(address,'ipv4_mapped',None) is not None or address.is_unspecified or address.is_multicast or address.is_link_local or address.is_reserved and not (local and address.is_loopback)
            or not local and not address.is_global):
            raise HTTPException(422,'模型端点包含禁止访问的网络地址')
    return base,sorted(addresses,key=lambda raw:(ipaddress.ip_address(raw).version,raw)),local


def _pool(parsed):
    context=ssl.create_default_context()
    proxy=getproxies().get(parsed.scheme) if not proxy_bypass(parsed.hostname or '') else None
    options={'ssl_context':context,'max_connections':1,'max_keepalive_connections':0,'retries':0}
    if not proxy:return httpcore.ConnectionPool(**options)
    p=urlsplit(proxy if '://' in proxy else 'http://'+proxy)
    if p.scheme not in {'http','https'} or not p.hostname:raise HTTPException(503,'当前网络代理协议不支持受控模型请求')
    auth=(unquote(p.username or ''),unquote(p.password or '')) if p.username is not None else None
    host='['+p.hostname+']' if ':' in p.hostname else p.hostname
    proxy_url=urlunsplit((p.scheme,host+(':'+str(p.port) if p.port else ''),'','',''))
    return httpcore.HTTPProxy(proxy_url=proxy_url,proxy_auth=auth,proxy_ssl_context=context,**options)


def request(provider,suffix,payload=None,method='POST'):
    if not suffix.startswith('/') or any(c in suffix for c in ('?','#','..','://')):raise HTTPException(422,'模型请求路径无效')
    base,addresses,local=resolve_endpoint(provider)
    parsed=urlsplit(base);selected=addresses[0]
    host='['+selected+']' if ':' in selected else selected
    netloc=host+(':'+str(parsed.port) if parsed.port else '')
    target=urlunsplit((parsed.scheme,netloc,parsed.path.rstrip('/')+suffix,'',''))
    data=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode() if payload is not None else b''
    if len(data)>MAX_REQUEST:raise HTTPException(413,'模型输入过大，请缩小素材或照片范围')
    headers={'Host':parsed.netloc,'Content-Type':'application/json','Accept':'application/json','Accept-Encoding':'identity'}
    if provider.key_env:
        secret=os.environ.get(provider.key_env,'')
        if not secret or any(ord(c)<33 or ord(c)>126 for c in secret):raise HTTPException(503,'模型密钥环境变量未配置或格式无效')
        if provider.kind=='anthropic':headers['x-api-key']=secret
        elif provider.kind=='gemini':headers['x-goog-api-key']=secret
        else:headers['Authorization']='Bearer '+secret
    if provider.kind=='anthropic':headers['anthropic-version']='2023-06-01'
    timeout=provider.timeout_seconds
    extensions={'sni_hostname':parsed.hostname,'timeout':{'connect':min(timeout,10),'read':timeout,'write':timeout,'pool':5}}
    deadline=time.monotonic()+timeout
    try:
        with _pool(parsed) as pool:
            with pool.stream(method,target,headers=headers,content=data,extensions=extensions) as response:
                if 300<=response.status<400:raise HTTPException(502,'模型服务返回重定向，已拒绝跟随')
                if response.status==402:raise HTTPException(502,'模型服务余额或配额不足，请检查服务账户')
                if response.status==404:raise HTTPException(502,'模型或端点不存在，请检查Model ID与Base URL')
                if response.status==429:raise HTTPException(429,'模型服务限流，请稍后重试；请先核对调用记录')
                if response.status in (401,403):raise HTTPException(502,'模型服务拒绝认证，请检查密钥与模型权限')
                if response.status!=200:raise HTTPException(502,'模型服务请求失败，请核对调用记录后重试')
                parts=[];size=0
                for chunk in response.iter_stream():
                    size+=len(chunk)
                    if size>MAX_RESPONSE:raise HTTPException(502,'模型响应超过安全大小限制')
                    if time.monotonic()>deadline:raise HTTPException(504,'模型响应超时；调用可能已计费，请核对调用记录')
                    parts.append(chunk)
        from .parsers import json_data
        return json_data(b''.join(parts))
    except HTTPException:raise
    except (httpcore.TimeoutException,TimeoutError):raise HTTPException(504,'模型请求超时；调用可能已计费，请核对调用记录') from None
    except Exception:raise HTTPException(502,'模型连接或JSON响应无效；未记录模型响应正文') from None


def post(provider,suffix,payload):
    return request(provider,suffix,payload)


def get(provider,suffix):
    return request(provider,suffix,method='GET')
