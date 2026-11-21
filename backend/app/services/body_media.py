"""Versioned private-media Markdown. References are derived, never client indexes."""
import json
import re
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select, delete
from markdown_it import MarkdownIt
from ..content_models import RecordBodyMedia, RevisionMediaRef
from ..archive_models import MediaAsset

MARKER=':::lj-media-v1'

class MediaStructureError(ValueError):
    """A recognized block has invalid container boundaries, not bad metadata."""


def media_parser(rule=None):
    parser=MarkdownIt('commonmark')
    # TipTap tight lists omit the optional blank line before block atoms. A
    # recognized media opener must terminate a paragraph, just like a fence.
    # _rule still enforces the container, exact indentation and all attributes.
    parser.block.ruler.before('fence','private_media',rule or _rule,{'alt':['paragraph']})
    return parser


def parse_media(body):
    try:return media_parser().parse(body)
    except MediaStructureError as exc:raise HTTPException(422,'私有图片块结构无效，请检查结束标记与列表缩进') from exc
    except json.JSONDecodeError as exc:raise HTTPException(422,'私有图片配置不是有效JSON，请保留完整图片块') from exc
    except (ValueError,TypeError,KeyError) as exc:raise HTTPException(422,'私有图片字段无效，请检查UUID、文字、尺寸和对齐') from exc


def valid_block(value):
    if not isinstance(value,dict) or set(value)-{'id','alt','caption','width','widthPercent','align','layout'}:
        raise ValueError('图片配置字段无效')
    if not isinstance(value.get('id'),str):raise ValueError('图片标识必须是UUID文本')
    UUID(value['id'])
    if str(UUID(value['id']))!=value['id']:raise ValueError('图片标识无效')
    for key,limit in [('alt',1000),('caption',2000)]:
        if not isinstance(value.get(key,''),str) or len(value.get(key,''))>limit:raise ValueError('图片文字超限')
    if value.get('align','center') not in ['left','center','right']:raise ValueError('图片对齐无效')
    if 'widthPercent' in value and (type(value['widthPercent']) is not int or value['widthPercent'] not in (30,60,100)):raise ValueError('图片百分比无效')
    if value.get('layout','auto') not in ('auto','single','grid'):raise ValueError('图片排列无效')
    width=value.get('width',960)
    if type(width) is not int or not 120<=width<=1600:raise ValueError('图片尺寸无效')
    return value


def _rule(state,start,end,silent):
    # A list's indentation is structural, not an indented code sample.
    # Quotes remain literal for backwards compatibility with quoted examples.
    if state.parentType not in ('root','paragraph','list') or state.sCount[start]!=state.blkIndent:return False
    def line_at(index):
        return state.src[state.bMarks[index]+state.tShift[index]:state.eMarks[index]]
    line=line_at(start)
    if line!=MARKER:return False
    if silent:return True
    if start+2>=end or line_at(start+2)!=':::':
        raise MediaStructureError('图片块未完整结束')
    if any(state.sCount[i]!=state.blkIndent for i in (start+1,start+2)):raise MediaStructureError('图片块缩进不一致')
    raw=line_at(start+1)
    value=valid_block(json.loads(raw))
    token=state.push('private_media','',0);token.meta=value;token.map=[start,start+3]
    state.line=start+3
    return True


def blocks(body,version):
    if version==1:return []
    if version!=2:raise HTTPException(422,'不支持的正文格式')
    return [t.meta for t in parse_media(body) if t.type=='private_media']


def sync_body(db,record):
    from .resource_usage import markdown_media_ids
    from .content import fields_for
    ids={m['id'] for m in blocks(record.body,record.body_format)} | markdown_media_ids(record.body)
    for f in fields_for(db,record.type_id,record.schema_version):
        value=record.values.get(f['id'])
        if f['kind']=='markdown' and isinstance(value,str):ids |= markdown_media_ids(value)
    from .experiences import media_ids
    if record.body_format==2:ids |= media_ids(record.body)
    active=set(db.scalars(select(MediaAsset.id).where(MediaAsset.id.in_(ids),MediaAsset.deleted_at.is_(None)))) if ids else set()
    if ids!=active:raise HTTPException(422,'正文包含不存在或已删除的图片，原输入仍保留')
    db.execute(delete(RecordBodyMedia).where(RecordBodyMedia.record_id==record.id))
    db.add_all(RecordBodyMedia(record_id=record.id,media_id=id) for id in ids)


def referenced_ids(snapshot):
    ids={m['id'] for m in blocks(snapshot.get('body',''),snapshot.get('body_format',1))}
    con=snapshot.get('connections') or {}
    ids.update(str(m['id']) for m in con.get('media',[]))
    life=snapshot.get('life') or {}
    for a in life.get('activities',[]):ids.update(str(id) for id in a.get('media_ids',[]))
    ids.update(str(p['media_id']) for p in life.get('photos',[]))
    from .experiences import media_ids
    if snapshot.get('body_format',1)==2:ids |= media_ids(snapshot.get('body',''))
    return ids


def snapshot_refs(db,record_id,number,snapshot):
    from .resource_usage import snapshot_media_ids
    ids=snapshot_media_ids(snapshot)
    # Historical references may point to an already-soft-deleted asset; retain them.
    found=set(db.scalars(select(MediaAsset.id).where(MediaAsset.id.in_(ids)))) if ids else set()
    db.add_all(RevisionMediaRef(record_id=record_id,number=number,media_id=id) for id in found)


def safe_excerpt(source,version=2,limit=220):
    """Readable text, with opaque media metadata removed before length limiting.

    Fail closed for malformed/unclosed media blocks without eating later prose.
    This is presentation only: never rewrite the stored Markdown.
    """
    kept=[];opaque=False
    for line in source.splitlines():
        stripped=re.sub(r'^\s*(?:>\s*)?(?:[-*+]\s+)?','',line)
        marker=re.search(r':::lj-(?:media|entry)-v\d+',stripped)
        if marker:
            if stripped[:marker.start()].strip():kept.append(stripped[:marker.start()])
            opaque=True;continue
        if opaque:
            if stripped.strip()==':::':opaque=False;continue
            if not stripped.strip() or re.match(r'^[{\[}\]"\s,]',stripped):continue
            opaque=False
        kept.append(line)
    tokens=MarkdownIt('commonmark').parse('\n'.join(kept));text=[]
    for token in tokens:
        if token.type=='inline':
            text.append(''.join(c.content if c.type in ('text','code_inline') else ' ' if c.type in ('softbreak','hardbreak') else '' for c in token.children or []))
        elif token.type in ('fence','code_block'):text.append(token.content)
    return re.sub(r'\s+',' ',' '.join(text)).strip()[:limit]


def narrative_parser():
    """Use the same container grammar, but treat media metadata as an opaque barrier.

    Literal legacy examples may be malformed. Their validation belongs to the
    versioned body validator, not place/itinerary inference.
    """
    def barrier(state,start,end,silent):
        try:return _rule(state,start,end,silent)
        except (ValueError,TypeError,KeyError):
            if silent:return True
            token=state.push('private_media_literal','',0);token.map=[start,min(start+3,end)]
            state.line=min(start+3,end);return True
    p=media_parser(barrier)
    from .experiences import rule
    def entry_barrier(state,start,end,silent):
        try:return rule(state,start,end,silent)
        except (ValueError,TypeError,KeyError):
            if silent:return True
            token=state.push('life_entry_literal','',0);token.map=[start,min(start+3,end)]
            state.line=min(start+3,end);return True
    p.block.ruler.before('fence','life_entry',entry_barrier,{'alt':['paragraph']})
    return p


def locations(body,version):
    if version!=2:return []
    return [(token.map[0]+1,token.meta) for token in parse_media(body) if token.type=='private_media']
