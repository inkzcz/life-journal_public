"""Canonical generators checked by the existing v5.1.4 parsers, not a new grammar."""
import json
import re
from uuid import UUID
from ..services.markdown_marks import parse
from ..services.body_media import MARKER, valid_block, blocks

RULE_VERSION = '1'
KINDS = {'l':'地点 / 地区','f':'美食 / 餐厅','s':'景点','h':'住宿','t':'交通','c':'咖啡 / 饮品','p':'购物'}


def place_mark(kind, name, place_id=None):
    if kind not in KINDS or not isinstance(name,str) or not name.strip() or len(name)>200:
        raise ValueError('地点类型或名称无效')
    if name!=name.strip() or any(c in name for c in ('\n','\r','\x00','@')) or '{#place:' in name:
        raise ValueError('地点名称含无法无歧义序列化的字符，请调整名称')
    # Use the existing spaced form; CommonMark backslash escaping is transparent
    # to the existing parser. Never let names create emphasis, code or HTML.
    escaped=re.sub(r'([\\`*_{}\[\]<>()!#|])',r'\\\1',name)
    pid=str(UUID(str(place_id))) if place_id is not None else None
    result='@'+kind+' '+escaped+(' {#place:'+pid+'}' if pid else '')
    parsed=parse(result).marks
    if len(parsed)!=1 or any(parsed[0][k]!=v for k,v in {'kind':kind,'name':name,'place_id':pid}.items()):
        raise ValueError('名称无法由现有标记语法无损表达')
    return result


def media_mark(value):
    clean=valid_block(dict(value))
    result=MARKER+'\n'+json.dumps(clean,ensure_ascii=False,separators=(',',':'))+'\n:::'
    if blocks(result,2)!=[clean]:raise ValueError('媒体标记未能无损序列化')
    return result


def registry():
    return {'rule_version':RULE_VERSION,'place_marks':[
        {'id':'@'+k,'name':v,'version':1,'required':['name'],'optional':['place_id'],
         'limits':{'name':200},'parameters_schema':{'type':'object','required':['name'],'additionalProperties':False,'properties':{'name':{'type':'string','minLength':1,'maxLength':200,'description':'不含换行、@或身份控制片段；必须通过原解析器往返验证。'},'place_id':{'anyOf':[{'type':'string','format':'uuid'},{'type':'null'}]}}},'parser':'services/markdown_marks.py:parse','renderer':'writing/places.ts','serializer':'exchange/syntax.py:place_mark','example':place_mark(k,'示例名称'),
         'invalid':'@'+k+'','notes':'空格/紧凑/方括号旧语法继续由原解析器读取；生成器使用已验证的空格形式。代码/URL不作为业务标记。'} for k,v in KINDS.items()],
        'private_media':{'id':MARKER,'version':1,'body_format':2,'required':['id'],
        'optional':['alt','caption','width','widthPercent','align','layout'],
        'parameters_schema':{'type':'object','required':['id'],'additionalProperties':False,'properties':{
            'id':{'type':'string','format':'uuid','pattern':r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'},
            'alt':{'type':'string','maxLength':1000},'caption':{'type':'string','maxLength':2000},
            'width':{'type':'integer','minimum':120,'maximum':1600,'default':960},'widthPercent':{'type':'integer','enum':[30,60,100]},
            'align':{'type':'string','enum':['left','center','right'],'default':'center'},'layout':{'type':'string','enum':['auto','single','grid'],'default':'auto'}}},
        'parser':'services/body_media.py:blocks','renderer':'reading/InlineMedia.vue','serializer':'exchange/syntax.py:media_mark',
        'width':{'minimum':120,'maximum':1600},'widthPercent':[30,60,100],
        'align':['left','center','right'],'layout':['auto','single','grid'],
        'notes':'UUID只能来自确认导入后的媒体映射或管理员明确选择的现有媒体；模型不能猜测UUID。'}}


def serialize(kind, parameters):
    """Single dispatch used by structured generation; unknown grammars fail closed."""
    if kind==MARKER:return media_mark(parameters)
    if kind not in {'@'+k for k in KINDS} or set(parameters)-{'name','place_id'}:
        raise ValueError('不支持的特殊语法或参数')
    return place_mark(kind[1],parameters.get('name'),parameters.get('place_id'))
