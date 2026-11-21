"""Offline deterministic extraction. Nothing is saved by preview."""
import re,hashlib,uuid
from datetime import date,timedelta
from markdown_it import MarkdownIt
from fastapi import HTTPException

def fingerprint(body):return hashlib.sha256(body.encode()).hexdigest()
NUMBERS={'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,'十一':11,'十二':12,'十三':13,'十四':14,'十五':15,'十六':16,'十七':17,'十八':18,'十九':19,'二十':20}
DATES=re.compile(r'(?P<iso>\d{4}-\d{1,2}-\d{1,2})|(?:(?P<year>\d{4})年)?(?P<month>\d{1,2})月(?P<day>\d{1,2})[日号]|第(?P<relative>\d{1,3}|[一二三四五六七八九十]{1,3})天')
TIME=re.compile(r'(?<!\d)([0-2]?\d)[:：]([0-5]\d)(?!\d)')

def resolve_day(match,start=None,end=None,*,bounded=True):
    """Shared date resolution for itinerary and Markdown-derived food indexes."""
    if match['iso']:value=date.fromisoformat(match['iso'])
    elif match['relative']:
        n=int(match['relative']) if match['relative'].isdigit() else NUMBERS.get(match['relative'])
        if not start or not n or n>300:raise ValueError('relative')
        value=start+timedelta(days=n-1)
    else:
        if not match['year'] and not start:raise ValueError('year')
        year=int(match['year']) if match['year'] else start.year
        value=date(year,int(match['month']),int(match['day']))
        if bounded and not match['year'] and value<start:value=date(year+1,value.month,value.day)
    if bounded and (start and value<start or end and value>end):raise ValueError('range')
    return value

def extract(body,start=None,end=None,*,activity_lines=None):
    context=None;items=[];warnings=[]
    # AST maps allow only ordinary paragraphs/headings/list items; fenced/HTML/media JSON excluded.
    from .body_media import narrative_parser
    parser=narrative_parser();media_lines=set();lines=body.splitlines()
    for i,line in enumerate(lines):
        if line==':::lj-media-v1' and i+2<len(lines) and lines[i+2]==':::':media_lines.update((i,i+1,i+2))
    units=[];depth=0;top_item=0;current=None
    for token in parser.parse(body):
        if token.type=='list_item_open':
            depth+=1
            if depth==1:top_item+=1
        elif token.type=='list_item_close':depth-=1
        elif token.type=='inline' and token.map:
            if depth>1 or depth==1 and current==top_item:
                if units:units[-1][2].append(token.content)
            elif depth==1:
                lines=token.content.splitlines();units.append([token.map[0],lines[0],lines[1:]]);current=top_item
            else:
                for offset,line in enumerate(token.content.splitlines()):units.append([token.map[0]+offset,line,[]])
    for index,line,description in units:
        if index in media_lines or line.strip().startswith((':::lj-media-v1','{"')):continue
        text=re.sub(r'^\s*(?:#{1,6}\s*|[-*+]\s+|\d+[.)]\s+|>\s*)','',line).strip()
        if not text:continue
        date_text=re.sub(r'\{#place:[a-f0-9-]{36}\}',lambda m:' '*len(m[0]),text)
        match=DATES.search(date_text)
        if activity_lines is not None:
            if line.strip().startswith('|'):continue
            if index+1 not in activity_lines and not (match and match.start()==0) and not TIME.search(text):continue
        if match:
            try:
                context=resolve_day(match,start,end)
            except (ValueError,OverflowError):
                context=None;warnings.append({'line':index+1,'message':'日期无效、超出范围或缺少旅行起始日期，请手工确认'});continue
            text=(text[:match.start()]+text[match.end():]).strip(' ·—:-：')
        if not context:continue
        tm=TIME.search(text);time=None
        if tm:
            hour=int(tm[1])
            if hour>23:warnings.append({'line':index+1,'message':'活动时间无效'});continue
            time=f'{hour:02d}:{tm[2]}';text=(text[:tm.start()]+text[tm.end():]).strip(' ·—:-：')
        if not text:continue
        # No guessing of locations or media. Only a coarse editable activity kind.
        kind='food' if re.search('早餐|午餐|晚餐|用餐|美食|品尝|餐厅',text) else 'transport' if re.search('火车|高铁|航班|乘车|交通|地铁',text) else 'sight' if re.search('游览|参观|景点|公园|博物馆',text) else 'other'
        key=fingerprint(context.isoformat()+'|'+str(time)+'|'+text)
        if any(x['source_key']==key for x in items):continue
        if len(text)>200:warnings.append({'line':index+1,'message':'活动标题超过200字，请手动整理'});continue
        items.append({'id':str(uuid.uuid5(uuid.NAMESPACE_URL,'life-journal-activity:'+key)),'source_key':key,'line':index+1,'day':context.isoformat(),'time':time,'title':text,'description':'\n'.join(description),'kind':kind,'place_id':None,'media_ids':[]})
        if len(items)>=300:warnings.append({'line':index+1,'message':'达到300项上限，其余请手动整理'});break
    return {'items':items,'warnings':warnings,'body_hash':fingerprint(body)}
