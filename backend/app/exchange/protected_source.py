"""Opaque, request-local preservation of authored business syntax.

The model can edit prose, but never reconstruct resource identities. Restore
only after its untrusted output has passed the ordinary Exchange validator.
"""
import re,secrets
from dataclasses import dataclass
from fastapi import HTTPException
from ..services.markdown_marks import parse
from ..services.body_media import blocks,narrative_parser
from ..services.resource_usage import markdown_media_ids
from ..services.itinerary import DATES
from ..services.experiences import entries

TOKEN=re.compile(r'\{\{lj-keep-[a-f0-9]{24}-\d+\}\}')

@dataclass(frozen=True)
class ProtectedSource:
    body:str
    fragments:tuple
    original:str
    hints:tuple
    media:tuple
    places:tuple

    def restore(self,body):
        expected=[key for key,_ in self.fragments]
        if TOKEN.findall(body)!=expected or body.count('{{lj-keep-')!=len(expected):
            raise ValueError('模型遗漏、重复或移动了受保护正文，请保留原文并重新固定范围')
        # Keeping bytes inside code/HTML is not preserving authored semantics.
        # Check actual Markdown text nodes before restoring opaque fragments.
        visible=set();lines=body.splitlines()
        for token in narrative_parser().parse(body):
            if token.type!='inline' or not token.map:continue
            for index in range(*token.map):
                raw=lines[index] if index<len(lines) else ''
                if raw in expected and any(child.type=='text' and raw in child.content for child in token.children or []):visible.add(raw)
        if visible!=set(expected):raise ValueError('受保护占位符必须保持为独立可见正文行，不能放入代码或HTML')
        for key,raw in self.fragments:body=body.replace(key,raw,1)
        signature=lambda text:[(m['kind'],m['name'],m.get('place_id'),m['region']) for m in parse(text).marks]
        try:card_unchanged=entries(body)==entries(self.original)
        except HTTPException:raise ValueError('模型破坏了受保护卡片，原文未修改') from None
        if signature(body)!=signature(self.original) or blocks(body,2)!=blocks(self.original,2) or markdown_media_ids(body)!=markdown_media_ids(self.original) or not card_unchanged:
            raise ValueError('模型改变了受保护内容的 Markdown 上下文，原文未修改')
        return body


def prepare(db,body,body_format=2):
    from ..archive_models import MediaAsset,Place
    if '{{lj-keep-' in body:raise HTTPException(422,'正文含保留占位符前缀，请改用普通文字后重新固定范围')
    media_blocks=blocks(body,2)
    if body_format==1 and (media_blocks or entries(body)):
        raise HTTPException(422,'旧格式正文含字面图片块，请仅选择不含图片块的文字；不会自动改变旧语法含义')
    document=parse(body);cards=entries(body);media_ids={m['id'] for m in media_blocks}|markdown_media_ids(body)|{mid for e in cards for mid in e['media_ids']}
    media=[];places=[]
    for id in sorted(media_ids):
        item=db.get(MediaAsset,id)
        if item is None or item.deleted_at:raise HTTPException(422,'正文引用的照片已不可用，未发送模型；请先核对资源')
        media.append({'key':'kept-media-'+str(len(media)),'existing_id':id})
    seen=set()
    for mark in document.marks:
        id=mark.get('place_id')
        if not id or id in seen:continue
        item=db.get(Place,id)
        if item is None or not item.active:raise HTTPException(422,'正文引用的地点已不可用，未发送模型；请先核对资源')
        seen.add(id);places.append({'key':'kept-place-'+str(len(places)),'kind':mark['kind'],'name':mark['name'],'existing_id':id})
    for card in cards:
        pid=card['fields'].get('place_id')
        if not pid or pid in seen:continue
        item=db.get(Place,pid)
        if not item or not item.active:raise HTTPException(422,'卡片地点不可用，未发送模型')
        seen.add(pid);places.append({'key':'kept-place-'+str(len(places)),'kind':card['kind'] if card['kind'] in ('l','f') else 'l','name':item.name,'existing_id':pid})
    lines=body.splitlines(keepends=True);protected=set()
    for line in document.lines:
        if line.marks or DATES.search(line.text):protected.add(line.number-1)
    for token in narrative_parser().parse(body):
        if not token.map:continue
        if token.type in ('private_media','private_media_literal','life_entry','life_entry_literal') or token.type=='inline' and markdown_media_ids(token.content):
            protected.update(range(*token.map))
    nonce=secrets.token_hex(12);output=[];fragments=[];hints=[];index=0
    while index<len(lines):
        if index not in protected:output.append(lines[index]);index+=1;continue
        start=index
        while index<len(lines) and index in protected:index+=1
        raw=''.join(lines[start:index]);key='{{lj-keep-'+nonce+'-'+str(len(fragments))+'}}'
        # Keep a line boundary outside the token so a model can lay out prose.
        ending='\r\n' if raw.endswith('\r\n') else '\n' if raw.endswith('\n') else ''
        fragments.append((key,raw[:-len(ending)] if ending else raw));output.append(key+ending)
        # The explicitly selected text already authorizes these names/dates.
        # Supply read-only facts, not opaque UUIDs, so itinerary generation can
        # understand a preserved date/restaurant without reconstructing syntax.
        facts=[]
        for line in document.lines:
            if not start<=line.number-1<index:continue
            text=re.sub(r'\{#place:[a-f0-9-]{36}\}', '',line.text).replace('\x00',' ').strip()
            if line.marks or DATES.search(text):facts.append(text[:2000])
        hints.append({'token':key,'facts':facts})
    return ProtectedSource(''.join(output),tuple(fragments),body,tuple(hints),tuple(media),tuple(places))


def restore(value,plan):
    from .schemas import Exchange
    if not plan.fragments:
        if '{{lj-keep-' in value.records[0].body:raise ValueError('模型伪造了保留占位符')
        return value
    data=value.model_dump(mode='json');data['records'][0]['body']=plan.restore(data['records'][0]['body'])
    data['media']+=list(plan.media);data['places']+=list(plan.places)
    return Exchange.model_validate(data)
