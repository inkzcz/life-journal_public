"""Structured notification templates; data never becomes JSON syntax or origin."""
import json,re
from urllib.parse import parse_qsl,urlencode,urlsplit

VARIABLES={'title','content','name','date','days_left','years','calendar_type'}
SLOTS=re.compile(r'\{\{|\}\}|\{([^{}]*)\}')
TOKEN=re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,64}\Z")
FORBIDDEN={'host','content-length','transfer-encoding','connection','keep-alive','proxy-authenticate','proxy-authorization','te','trailer','upgrade','expect','content-type','accept-encoding'}
TYPES={'json':'application/json','form':'application/x-www-form-urlencoded','text':'text/plain; charset=utf-8'}


def text(value,variables):
    def replace(match):
        raw=match[0]
        if raw=='{{':return '{'
        if raw=='}}':return '}'
        key=match[1]
        if key=='':return '{}'
        if key not in VARIABLES:raise ValueError('不支持的通知变量或格式化语法')
        return str(variables.get(key,''))
    return SLOTS.sub(replace,value)


def structured(value,variables,depth=0):
    if depth>16:raise ValueError('通知JSON嵌套过深')
    if isinstance(value,str):return text(value,variables)
    if isinstance(value,list):return [structured(v,variables,depth+1) for v in value]
    if isinstance(value,dict):
        if any('{' in k or '}' in k for k in value):raise ValueError('JSON键不接受通知变量')
        return {k:structured(v,variables,depth+1) for k,v in value.items()}
    return value


def loads(value):
    def invalid(_):raise ValueError('通知JSON必须使用标准JSON值')
    return json.loads(value,parse_constant=invalid)


def legacy_json_structure(value):
    out=[];i=0;quoted=False
    while i<len(value):
        c=value[i]
        if quoted and c=='\\' and i+1<len(value):out.extend(value[i:i+2]);i+=2;continue
        if c=='"':quoted=not quoted
        if not quoted and value[i:i+2] in ('{{','}}'):out.append(c);i+=2
        else:out.append(c);i+=1
    return ''.join(out)


def query_value(value,variables):
    # Normal JSON needs no doubling of structural braces. Legacy explicitly
    # escaped braces and simple placeholders keep their existing text behavior.
    if any(value.lstrip().startswith('{'+key+'}') for key in VARIABLES):return text(value,variables)
    if value.lstrip().startswith('{{'):
        try:parsed=loads(legacy_json_structure(value))
        except (ValueError,RecursionError):pass
        else:return json.dumps(structured(parsed,variables),ensure_ascii=False,separators=(',',':'),allow_nan=False)
    if value.lstrip().startswith(('{','[')) and not value.lstrip().startswith('{{'):
        try:parsed=loads(value)
        except (ValueError,RecursionError):
            if value.lstrip().startswith('[') and '{' not in value and '}' not in value:return text(value,variables)
            if value not in ('{'+key+'}' for key in VARIABLES):
                raise ValueError('复杂查询参数须使用有效JSON或已知变量') from None
        else:return json.dumps(structured(parsed,variables),ensure_ascii=False,separators=(',',':'),allow_nan=False)
    return text(value,variables)


def headers(rows,variables):
    if len(rows)>20:raise ValueError('通知请求头过多')
    output={};size=0
    for row in rows:
        name=row['name'];value=text(row['value'],variables)
        if not TOKEN.fullmatch(name) or name.lower() in FORBIDDEN or name.lower() in {k.lower() for k in output}:
            raise ValueError('通知请求头名称无效、重复或属于传输控制字段')
        if len(value)>2048 or any(ord(c)<32 or ord(c)==127 for c in value):raise ValueError('通知请求头值无效')
        size+=len(name.encode())+len(value.encode())
        if size>8192:raise ValueError('通知请求头总长度超限')
        output[name]=value
    return output


def build(config,variables):
    from .transport import render
    method=config.get('method','GET');fmt=config.get('body_format','json')
    if method not in ('GET','POST') or fmt not in TYPES:raise ValueError('通知请求方法或格式无效')
    url=render(config['url_template'],variables)
    request_headers=headers(config.get('headers',[]),variables);body=b''
    if method=='POST':
        source=config.get('body_template','')
        if len(source)>32000:raise ValueError('通知请求体模板过长')
        try:
            if fmt=='json':body=json.dumps(structured(loads(source),variables),ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
            elif fmt=='form':
                pairs=parse_qsl(source,keep_blank_values=True)
                if any('{' in k or '}' in k for k,v in pairs):raise ValueError()
                body=urlencode([(k,query_value(v,variables)) for k,v in pairs]).encode()
            else:body=text(source,variables).encode()
        except (ValueError,TypeError,RecursionError,UnicodeError):raise ValueError('通知请求体模板无效') from None
        request_headers['Content-Type']=TYPES[fmt]
    if len(body)>65536:raise ValueError('通知请求体超过64KiB')
    return {'method':method,'url':url,'headers':request_headers,'body':body,'body_format':fmt}


def validate(config):
    if not config.get('url_template'):
        if config.get('enabled'):raise ValueError('启用通知前必须填写URL')
        # Validate header/body syntax without inventing a network target to send.
        config={**config,'url_template':'https://example.invalid/'}
    build(config,{key:'' for key in VARIABLES})


def preview(config,variables):
    request=build(config,variables);origin=urlsplit(request['url'])
    def shape(value):
        if isinstance(value,dict):return {k:shape(v) for k,v in value.items()}
        if isinstance(value,list):return [shape(v) for v in value]
        return '[REDACTED]'
    body='[REDACTED]' if request['body'] else ''
    if request['method']=='POST' and request['body_format']=='json':body=shape(loads(request['body']))
    return {'method':request['method'],'url':origin.scheme+'://'+origin.netloc+'/[path-and-query-redacted]',
        'headers':{k:v if k=='Content-Type' else '[REDACTED]' for k,v in request['headers'].items()},
        'body':body,'body_format':request['body_format'],'body_bytes':len(request['body']),
        'template_result':'valid','external_request_sent':False,'network_policy_checked':False,
        'redaction_note':'路径/查询及请求体值整体隐藏，未知秘密格式不能可靠分类；预览不发请求。'}
