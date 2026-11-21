"""Server-only compilation to existing Markdown and RecordCreate. No DB writes."""
import hashlib,re,uuid
from fastapi import HTTPException
from ..services.markdown_marks import parse
from ..services.body_media import blocks
from ..services.experiences import entries
from ..services.resource_usage import markdown_media_ids
from .preview import placeholders
from .syntax import media_mark,place_mark


def literal(text):
    return re.sub(r'([\\`*_{}\[\]<>()!#|+.\-])',r'\\\1',text)


def compile_record(record,prepared,media_ids,place_ids,record_id,new_media_ids=()):
    """Transport keys are replaced only using server-resolved, validated identities."""
    media={m.key:m for m in prepared.media};places={p.key:p for p in prepared.places}
    def image(key):
        m=media[key];attrs={k:getattr(m,k) for k in ('alt','caption','width','widthPercent','align','layout') if getattr(m,k) is not None}
        return media_mark({'id':media_ids[key],**attrs})
    body=record.body;used_media=list(record.media_keys);used_places=[]
    lines=body.splitlines(keepends=True)
    slots=placeholders(body)
    used_media += [s['key'] for s in slots if s['kind']=='media']
    used_places += [s['key'] for s in slots if s['kind']=='place']
    for slot in reversed(slots):
        raw=lines[slot['line']];indent=raw[:len(raw)-len(raw.lstrip())]
        if slot['kind']=='media':text=image(slot['key'])
        else:
            p=places[slot['key']];text=place_mark(p.kind,p.name,place_ids[slot['key']])
        lines[slot['line']]='\n'.join(indent+s for s in text.splitlines())+('\n' if raw.endswith('\n') else '')
    body=''.join(lines)
    if record.foods and any(m['kind']=='f' for m in parse(body).marks):raise HTTPException(422,'结构化foods与正文@f不能重复描述同一来源，请选择一种表示后重新预览')
    expected=[]
    for food in record.foods:
        p=places[food.place_key]
        if parse(food.review).marks or ':::lj-media-v' in food.review:raise HTTPException(422,'评价请使用普通文字；地点和图片通过结构化字段明确关联')
        if food.day:
            if record.travel and (record.travel.start_date and food.day<record.travel.start_date or record.travel.end_date and food.day>record.travel.end_date):raise HTTPException(422,'用餐日期超出旅行范围')
            body+='\n\n## '+food.day.isoformat()+'\n\n'
        else:body+='\n\n'
        body+='- '+(food.time+' ' if food.time else '')+place_mark('f',p.name,place_ids[p.key])
        for text in food.review.splitlines():
            if text:body+='\n  - '+literal(text)
        for key in food.media_keys:body+='\n\n'+'\n'.join('  '+s for s in image(key).splitlines())
        used_media+=food.media_keys;used_places.append(p.key)
        expected.append((p.name,place_ids[p.key],food.day))
        if len(body)>300000:raise HTTPException(422,'生成后的正文超过300000字符，请拆分内容后预览')
    if len(body)>300000:raise HTTPException(422,'生成后的正文超过300000字符')
    # The old grammar carries date context. Reject ambiguous missing-date cases
    # instead of silently inheriting a previous day or inventing a new date.
    if expected:
        rows=parse(body).food(record.travel.start_date if record.travel and record.travel.start_date else record.display_date,
                              record.travel.end_date if record.travel else None,bounded=bool(record.travel and record.travel.start_date))
        actual=[(row['mark']['name'],row['mark']['place_id'],row['day']) for row in rows]
        if actual!=expected:raise HTTPException(422,'餐厅日期无法无歧义表达，请补充实际日期或调整日期上下文；不会猜测或修改原文')
    life={'start_date':record.travel.start_date if record.travel else None,'end_date':record.travel.end_date if record.travel else None,'activities':[],'photos':[]}
    for a in record.travel.activities if record.travel else []:
        life['activities'].append({'id':str(uuid.uuid5(uuid.UUID(record_id),'exchange:'+a.key)),'day':a.day,'time':a.time,'title':a.title,'description':a.description,'kind':a.kind,
            'place_id':place_ids[a.place_key] if a.place_key else None,'media_ids':[media_ids[k] for k in a.media_keys]})
        used_media+=a.media_keys
        if a.place_key:used_places.append(a.place_key)
    owned=[]
    if record.travel and record.travel.start_date:
        for index,food in enumerate(record.foods):
            if food.day is None:continue
            if any(a.kind=='food' and a.place_key==food.place_key and a.day==food.day and a.time==food.time for a in record.travel.activities):
                raise HTTPException(422,'同次餐饮同时出现在foods与食物活动中，请明确保留一种来源；不会猜测合并或重复计数')
            # Each explicit food appearance is a distinct visit, including two
            # meals at the same restaurant/day without a clock time. IDs are
            # server-derived and replay-stable; the old Markdown parser remains
            # authoritative for the body/index, which is counted only once.
            source_key=hashlib.sha256(('exchange-food-v1:'+str(index)).encode()).hexdigest()
            id=str(uuid.uuid5(uuid.UUID(record_id),source_key));owned.append(id)
            life['activities'].append({'id':id,'source_key':source_key,'day':food.day,'time':food.time,'title':places[food.place_key].name,
                'description':food.review,'kind':'food','place_id':place_ids[food.place_key],'media_ids':[media_ids[k] for k in food.media_keys]})
    for p in record.photos:
        life['photos'].append({'media_id':media_ids[p.media_key],'taken_on':p.taken_on,'group_name':p.group_name,'place_id':place_ids[p.place_key] if p.place_key else None})
        used_media.append(p.media_key)
        if p.place_key:used_places.append(p.place_key)
    if record.cover_key:used_media.insert(0,record.cover_key)
    used_media=list(dict.fromkeys(used_media));used_places=list(dict.fromkeys(used_places))
    # Raw authored private blocks are allowed only when explicitly declared as
    # existing media. They still participate in normal current/history refs.
    used_ids={media_ids[k] for k in used_media}|{m['id'] for m in blocks(body,2)}|markdown_media_ids(body)|{mid for e in entries(body) for mid in e['media_ids']}
    declared=set(media_ids.values())
    if used_ids-declared:raise HTTPException(422,'正文存在未声明的私有媒体，不能猜测身份')
    links=[{'id':media_ids[k],'cover':k==record.cover_key,'caption':media[k].caption} for k in used_media]
    from ..life_schemas import LifeIn
    from ..archive_schemas import Connections
    from pydantic import ValidationError
    connections={'media':links,'places':list(dict.fromkeys(place_ids[k] for k in used_places)),'links':[]}
    try:
        LifeIn.model_validate(life);Connections.model_validate(connections)
    except ValidationError:raise HTTPException(422,'行程、照片或关联不符合现有字段约束，请修正后重新预览') from None
    return {'body':body,'life':life,'connections':connections,
            'new_media_ids':[id for id in used_ids if id in new_media_ids],'markdown_activity_ids':owned,'used_media_ids':used_ids}
