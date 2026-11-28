"""One bounded parser/synchronizer for source-authored structured experiences.

Canonical source UUIDs, not names/positions, define identity. Historical @l/@f
remain owned by their compatibility parsers. Parsing never alters a read.
"""
import json
import re
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import HTTPException
from markdown_it import MarkdownIt
from sqlalchemy import select
from ..models import now
from ..experience_models import Experience, ArticleOptions, ExperienceMedia

MARKER = ':::lj-entry-v1'
KINDS = {'l': '地点', 'f': '美食', 'm': '电影', 's': '演出', 'g': '礼物', 't': '交通'}
TEXT_FIELDS = {'date','time','cinema','screen','review','rating','show_type','performer','venue','seat',
               'direction','person','occasion','description','transport_type','departure','destination',
               'departure_at','arrival_at','departure_zone','arrival_zone','departure_station','arrival_station',
               'terminal','cabin','place_id'}


def validate(value, *, published=False):
    if not isinstance(value, dict) or set(value) - {'id','kind','name','fields','media_ids'}:
        raise ValueError('卡片字段无效')
    if str(uuid.UUID(value['id'])) != value['id'] or value['kind'] not in KINDS:
        raise ValueError('卡片身份或类型无效')
    if not isinstance(value['name'], str) or not value['name'].strip() or len(value['name']) > 200:
        raise ValueError('请填写卡片名称（最多200字）')
    fields = value.get('fields', {})
    if (not isinstance(fields, dict) or len(fields)>96
            or any(not isinstance(k,str) or not 1<=len(k)<=80 or any(ord(c)<32 for c in k) or k in ('__proto__','prototype','constructor') for k in fields)):
        raise ValueError('结构化字段无效')
    if any(not isinstance(v, str) or len(v) > 4000 for v in fields.values()):
        raise ValueError('结构化字段必须是4000字以内的文字')
    mids = value.get('media_ids', [])
    if not isinstance(mids, list) or len(mids) > 100 or len(set(mids)) != len(mids):
        raise ValueError('卡片图片重复或超过100张')
    for mid in mids:
        if not isinstance(mid, str) or str(uuid.UUID(mid)) != mid:raise ValueError('图片标识无效')
    if fields.get('date'):date.fromisoformat(fields['date'])
    if fields.get('place_id'):uuid.UUID(fields['place_id'])
    if value['kind'] == 't':
        required = ('transport_type','departure','destination','departure_at','arrival_at','departure_zone','arrival_zone')
        if published and any(not fields.get(k) for k in required):
            raise ValueError('发布交通卡片前请填写类型、起终点、完整出发/到达时间及时区')
        stamps = []
        for prefix in ('departure','arrival'):
            stamp, zone = fields.get(prefix+'_at'), fields.get(prefix+'_zone')
            if zone:ZoneInfo(zone)
            if stamp:
                dt = datetime.fromisoformat(stamp)
                if dt.tzinfo is None or dt.utcoffset() is None:raise ValueError('交通时间必须包含明确的UTC偏移')
                if zone and dt.astimezone(ZoneInfo(zone)).utcoffset() != dt.utcoffset():
                    raise ValueError('交通时间偏移与所选时区不一致')
                stamps.append(dt)
        if len(stamps) == 2 and stamps[1] < stamps[0]:raise ValueError('到达时间不能早于出发时间')
    return {'id':value['id'], 'kind':value['kind'], 'name':value['name'].strip(), 'fields':fields, 'media_ids':mids}


def rule(state, start, end, silent):
    if state.parentType not in ('root','paragraph','list') or state.sCount[start] != state.blkIndent:return False
    line = lambda i: state.src[state.bMarks[i]+state.tShift[i]:state.eMarks[i]]
    if line(start) != MARKER:
        if re.fullmatch(r':::lj-entry-v\d+',line(start)):raise ValueError('不支持的卡片版本')
        return False
    if silent:return True
    if start+2 >= end or line(start+2) != ':::' or any(state.sCount[i] != state.blkIndent for i in (start+1,start+2)):
        raise ValueError('结构化卡片未完整结束')
    value = validate(json.loads(line(start+1)))
    token = state.push('life_entry','',0);token.meta=value;token.map=[start,start+3]
    state.line=start+3
    return True


def parser():
    p = MarkdownIt('commonmark')
    p.block.ruler.before('fence','life_entry',rule,{'alt':['paragraph']})
    return p


def entries(body, *, published=False):
    try:
        found = [validate(t.meta, published=published) for t in parser().parse(body) if t.type=='life_entry']
        if len(found)>500:raise ValueError('单篇最多500条结构化记录')
        if len({x['id'] for x in found}) != len(found):raise ValueError('正文卡片ID重复，请使用编辑器复制卡片以分配新身份')
        return found
    except (ValueError,TypeError,KeyError,ZoneInfoNotFoundError):
        raise HTTPException(422,'结构化卡片无效、身份重复或交通信息不完整，请检查卡片；原正文未覆盖') from None


def serialize(value):return MARKER+'\n'+json.dumps(value, ensure_ascii=False, separators=(',',':'))+'\n:::'


def normalize_quick(body,previous_body=None,*,modern=True):
    """Normalize explicit structured copies only; text shortcuts require UI consent.

    Saving an article is not confirmation of an @ insertion dialog. In particular,
    cancellation must preserve literal shortcuts across later saves. Existing
    structured blocks and legacy marker parsers retain their original semantics.
    """
    lines=body.splitlines(keepends=True);replacements={};seen=set()
    try:tokens=parser().parse(body)
    except (ValueError,TypeError,KeyError):return body
    for token in tokens:
        if token.type!='life_entry':continue
        value=token.meta
        if value['id'] in seen:
            value={**value,'id':str(uuid.uuid4())}
            line=token.map[0]+1;pad=lines[line][:len(lines[line])-len(lines[line].lstrip())]
            replacements[line]=pad+json.dumps(value,ensure_ascii=False,separators=(',',':'))+('\n' if lines[line].endswith('\n') else '')
        seen.add(value['id'])
    return ''.join(replacements.get(i,line) for i,line in enumerate(lines))


def media_ids(body):return {mid for e in entries(body) for mid in e['media_ids']}


def sync(db, record):
    found=entries(record.body, published=record.status=='published') if record.body_format==2 else []
    from ..archive_models import MediaAsset
    mids={mid for e in found for mid in e['media_ids']}
    if mids!=set(db.scalars(select(MediaAsset.id).where(MediaAsset.id.in_(mids),MediaAsset.deleted_at.is_(None)))):raise HTTPException(422,'卡片包含不存在或已删除的图片')
    rows={x.id:x for x in db.scalars(select(Experience).where(Experience.record_id==record.id))}
    for row in rows.values():row.active=False
    for ref in db.scalars(select(ExperienceMedia).where(ExperienceMedia.record_id==record.id)):ref.active=False
    if record.deleted_at:return
    for pos, value in enumerate(found):
        fields=dict(value['fields'])
        if fields.get('place_id'):
            from .places import canonical
            fields['place_id']=canonical(db,fields['place_id'])
        row=rows.get(value['id'])
        if row and row.kind!=value['kind']:raise HTTPException(409,'已有卡片不能改变类型，请新增另一张卡片')
        if row is None:
            row=Experience(record_id=record.id,id=value['id'],created_at=now());db.add(row)
        row.kind=value['kind'];row.name=value['name'];row.fields={**fields,'media_ids':value['media_ids']}
        row.position=pos;row.active=True;row.updated_at=now()
        db.flush()
        for index,mid in enumerate(value['media_ids']):
            ref=db.get(ExperienceMedia,(record.id,value['id'],mid))
            if ref is None:ref=ExperienceMedia(record_id=record.id,entry_id=value['id'],media_id=mid);db.add(ref)
            ref.active=True;ref.position=index
    db.flush()


def syntax_version(db,record):
    from ..content_models import RecordRevision
    # Read only the protocol scalar; a historical body/media snapshot can be large.
    value=db.scalar(select(RecordRevision.snapshot['marker_version']).where(RecordRevision.record_id==record.id,RecordRevision.number==1))
    return value if type(value)is int and value in (1,2) else 1


def options(db, record):
    row=db.get(ArticleOptions, record.id)
    if row:return {'end_date':row.end_date.isoformat() if row.end_date else None,'travel_enabled':row.travel_enabled}
    from .record_mode import record_modes
    return {'end_date':None,'travel_enabled':record_modes(db,[record])[record.id]}


def save_options(db, record, data):
    if data is None:
        old=db.get(ArticleOptions,record.id)
        if old and old.end_date and old.end_date<record.display_date:raise HTTPException(422,'文章开始日期已超过现有结束日期，请一起调整日期范围')
        return
    end=data.end_date
    if end and end<record.display_date:raise HTTPException(422,'文章结束日期不能早于开始日期')
    row=db.get(ArticleOptions,record.id)
    if row is None:row=ArticleOptions(record_id=record.id);db.add(row)
    row.end_date=end;row.travel_enabled=data.travel_enabled


from .record_mode import record_modes
