"""Rebuildable food appearances. Markdown/content remains the only authoring source."""
import uuid,hashlib
from collections import Counter
from sqlalchemy import select
from ..v5_models import FoodOccurrence,FoodContentType
from ..archive_models import Place,RecordMarkedPlace
from ..life_models import TripActivity,TripPlan
from ..content_models import RecordRevision
from .marked_places import key
from .markdown_marks import parse,document

def appearances(body,start):
    return parse(body).food(start)


def sync(db,record):
    previous={r.source_key:r for r in db.scalars(select(FoodOccurrence).where(FoodOccurrence.record_id==record.id))}
    for row in previous.values():row.active=False
    if record.deleted_at:return
    bindings={r.source_key:r.place_id for r in db.scalars(select(RecordMarkedPlace).where(RecordMarkedPlace.record_id==record.id))}
    plan=db.get(TripPlan,record.id);counts=Counter();legacy_counts=Counter();sources=[]
    for item in document(db,record).food(plan.start_date if plan and plan.start_date else record.display_date,plan.end_date if plan else None,bounded=bool(plan and plan.start_date)):
        mark=item['mark'];pid=bindings.get(key(mark,mark['region']))
        place=db.get(Place,pid) if pid else None
        if not place:
            from fastapi import HTTPException
            raise HTTPException(422,'美食标记缺少明确地点绑定，请先编辑保存来源文章；未创建不完整索引')
        identity=mark.get('place_id') or hashlib.sha256((mark['name']+'|'+item['region']).encode()).hexdigest()
        counts[identity]+=1
        # Preserve an old heading-reset food identity (and manual overrides) only
        # when its exact source key/name and non-conflicting place agree.
        legacy=mark.get('place_id') or hashlib.sha256((mark['name']+'|'+mark['legacy_region']).encode()).hexdigest()
        legacy_counts[legacy]+=1
        sources.append({'source_key':'mark:'+identity+':'+str(counts[identity]),'legacy_source_key':'mark:'+legacy+':'+str(legacy_counts[legacy]),'source_kind':'mark','name':mark['name'],
            'description':'\n'.join(item['description']),'day':item['day'],'place_id':pid,
            'city':place.city or place.region or item['region'],'city_source':'place' if place.city or place.region else 'markdown_context' if item['region'] else 'unknown'})
    for a in db.scalars(select(TripActivity).where(TripActivity.record_id==record.id,TripActivity.active.is_(True))):
        if a.kind!='food' or a.markdown_owned:continue
        p=db.get(Place,a.place_id) if a.place_id else None
        sources.append({'source_key':'activity:'+a.id,'source_kind':'activity','name':a.dish or a.title,
            'description':'\n'.join(x for x in [a.description,a.experience] if x),'day':a.day,'place_id':a.place_id,
            'city':p.city if p else '', 'city_source':'place' if p and p.city else 'unknown'})
    if db.get(FoodContentType,record.type_id):
        info=article_info(db,record)
        from .body_media import safe_excerpt
        from datetime import date
        sources.append({'source_key':'article','source_kind':'article','name':info.get('food_shop') or record.title,'description':safe_excerpt(info.get('food_review') or record.summary or record.body,record.body_format,300),
            'day':date.fromisoformat(info['food_date']) if info.get('food_date') else None,'place_id':None,'city':info.get('food_city') or '','city_source':'field' if info.get('food_city') else 'unknown'})
    from .experiences import entries
    for e in entries(record.body) if record.body_format==2 else []:
        if e['kind']!='f':continue
        f=e['fields'];pid=f.get('place_id')
        if pid:
            from .places import canonical
            pid=canonical(db,pid)
        p=db.get(Place,pid) if pid else None
        if pid and (not p or not p.active):
            from fastapi import HTTPException
            raise HTTPException(422,'美食卡片地点不存在或已停用')
        from datetime import date
        sources.append({'source_key':'entry:'+e['id'],'source_kind':'mark','name':e['name'],'description':f.get('review',f.get('description','')),'day':date.fromisoformat(f['date']) if f.get('date') else None,'place_id':pid,'city':p.city if p else '', 'city_source':'place' if p else 'unknown'})
    if len(sources)>500: # Bounded writes, never truncate silently.
        from fastapi import HTTPException
        raise HTTPException(422,'单篇美食出现记录超过500项，请拆分文章')
    # A legacy row may have no place_id because of the bug being repaired. Its
    # latest saved source, not today's name/order, must prove the same identity.
    legacy_map=None
    used=set()
    for data in sources:
        legacy_key=data.pop('legacy_source_key',None)
        row=previous.get(data['source_key'])
        if row is None and legacy_key:
            candidate=previous.get(legacy_key)
            if candidate and candidate.name==data['name']:
                if legacy_map is None:
                    snapshot=db.scalar(select(RecordRevision).where(RecordRevision.record_id==record.id).order_by(RecordRevision.number.desc()).limit(1))
                    old_body=snapshot.snapshot['body'] if snapshot else record.body
                    old_counts=Counter();new_counts=Counter();legacy_map={}
                    for old in parse(old_body).marks:
                        if old['kind']!='f':continue
                        stable=old.get('place_id') or hashlib.sha256((old['name']+'|'+old['region']).encode()).hexdigest()
                        legacy=old.get('place_id') or hashlib.sha256((old['name']+'|'+old['legacy_region']).encode()).hexdigest()
                        old_counts[legacy]+=1;new_counts[stable]+=1
                        legacy_map['mark:'+legacy+':'+str(old_counts[legacy])]='mark:'+stable+':'+str(new_counts[stable])
                if legacy_map.get(legacy_key)!=data['source_key']:
                    candidate=None
                from .places import canonical
                if candidate and candidate.place_id and canonical(db,candidate.place_id)!=data['place_id']:
                    from fastapi import HTTPException
                    raise HTTPException(409,'历史美食地点身份存在冲突，拒绝自动重新绑定，请核对来源文章')
                row=candidate
        if row is not None:
            if row.id in used:
                from fastapi import HTTPException
                raise HTTPException(409,'历史美食来源身份不明确，拒绝自动合并')
            data['source_key']=row.source_key
            used.add(row.id)
        if not row:
            row=FoodOccurrence(id=str(uuid.uuid5(uuid.UUID(record.id),'food:'+data['source_key'])),record_id=record.id,**data)
            db.add(row)
        else:
            for k,v in data.items():setattr(row,k,v)
            row.revision+=1
        row.active=True
    db.flush()


def article_info(db,record):
    """Optional versioned dynamic fields, identified by purpose rather than name."""
    from .content import fields_for
    cache=db.info.setdefault('food_fields',{})
    k=(record.type_id,record.schema_version)
    if k not in cache:cache[k]=fields_for(db,*k)
    fields=cache[k]
    return {f['purpose']:record.values.get(f['id']) for f in fields if f.get('purpose') and f['active'] and record.values.get(f['id']) is not None}


def mark_media(db,record):
    """Only media nested inside one explicit @f list item belongs to that visit.

    Root-level article covers and ambiguous multi-restaurant items are NOT visits.
    No persisted association or original file is mutated.
    """
    from .body_media import narrative_parser
    doc=document(db,record);by_line={l.number:l for l in doc.lines};owners={};path=[];ordinal=0;counts=Counter();legacy_counts=Counter();result={}
    for token in narrative_parser().parse(record.body):
        if token.type=='list_item_open':ordinal+=1;path.append(ordinal)
        elif token.type=='list_item_close':path.pop()
        elif token.type=='inline' and token.map:
            for line_no in range(token.map[0]+1,token.map[1]+1):
                line=by_line.get(line_no)
                marks=[m for m in line.marks if m['kind']=='f'] if line else []
                keys=[]
                for m in marks:
                    identity=m.get('place_id') or hashlib.sha256((m['name']+'|'+m['region']).encode()).hexdigest();counts[identity]+=1
                    legacy=m.get('place_id') or hashlib.sha256((m['name']+'|'+m['legacy_region']).encode()).hexdigest();legacy_counts[legacy]+=1
                    keys.extend(['mark:'+identity+':'+str(counts[identity]),'mark:'+legacy+':'+str(legacy_counts[legacy])])
                if path and marks:owners[tuple(path)]=keys if len(marks)==1 else []
        elif token.type=='private_media' and path:
            owner=next((owners[tuple(path[:n])] for n in range(len(path),0,-1) if tuple(path[:n]) in owners),[])
            for k in owner:result.setdefault(k,[]).append(token.meta['id'])
    from .experiences import entries
    for e in entries(record.body) if record.body_format==2 else []:
        if e['kind']=='f':result['entry:'+e['id']]=e['media_ids']
    return result
