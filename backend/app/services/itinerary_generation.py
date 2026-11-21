"""Confirmed itinerary reconciliation, with durable resource audit evidence.

No authored Markdown is rewritten. Source keys identify generated activities;
manual activities and manually edited generated activities are never replaced.
"""
import copy
import re
import uuid
from datetime import date
from sqlalchemy import select
from fastapi import HTTPException
from ..archive_models import ResourceReferenceAudit, RecordMarkedPlace
from ..life_models import TripActivity, TripPlan
from .itinerary import extract, fingerprint


def audit_key(id):return 'ig:'+str(id)


def state(db,r):
    audit=db.get(ResourceReferenceAudit,audit_key(r.id))
    if not audit:
        exists=db.scalar(select(TripActivity.id).where(TripActivity.record_id==r.id,TripActivity.active.is_(True)).limit(1))
        return {'status':'needs_review' if exists else 'not_generated','message':''}
    value=dict(audit.value)
    if value.get('body_hash')!=fingerprint(r.body):value['status']='body_updated'
    return value


def record_audit(db,r,status,message=''):
    key=audit_key(r.id);row=db.get(ResourceReferenceAudit,key)
    value={'version':1,'status':status,'body_hash':fingerprint(r.body),'revision':r.revision,'message':message}
    if row:row.value=value
    else:db.add(ResourceReferenceAudit(key=key,value=value))


def proposal(db,r):
    from .life import life_data
    from .markdown_marks import document
    life=life_data(db,r.id)
    if not life['start_date']:raise HTTPException(422,'请先填写并保存旅行出发日期，再提取行程')
    marks=document(db,r).marks
    physical=r.body.splitlines()
    activity_lines={mark['line'] for mark in marks}|{index+1 for index,line in enumerate(physical) if re.match(r'^\s*(?:[-*+]|\d+[.)])\s',line)}
    # Filter before the extractor's 300-activity bound; long story paragraphs
    # must neither become activities nor crowd genuine later activities out.
    result=extract(r.body,date.fromisoformat(life['start_date']),date.fromisoformat(life['end_date']) if life['end_date'] else None,activity_lines=activity_lines)
    bindings={binding.source_key:binding.place_id for binding in db.scalars(select(RecordMarkedPlace).where(RecordMarkedPlace.record_id==r.id))}
    from .marked_places import key
    existing=list(db.scalars(select(TripActivity).where(TripActivity.record_id==r.id,TripActivity.active.is_(True))))
    by_key={a.source_key:a for a in existing if a.source_key}
    changes=[];conflicts=[];seen=set();order=[]
    from .body_media import locations
    media=locations(r.body,r.body_format);lines=r.body.splitlines()
    for item in result['items']:
        item={k:v for k,v in item.items() if k!='line'};seen.add(item['source_key'])
        old=by_key.get(item['source_key'])
        row=next(i for i in result['items'] if i['source_key']==item['source_key'])
        line_marks=[mark for mark in marks if mark['line']==row['line']]
        if line_marks:
            item['title']=' · '.join(mark['name'] for mark in line_marks)[:200]
            item['place_id']=next((bindings.get(key(mark,mark['region'])) for mark in reversed(line_marks) if bindings.get(key(mark,mark['region']))),None)
            kinds={'f':'food','s':'sight','t':'transport'}
            item['kind']=next((kinds[m['kind']] for m in line_marks if m['kind'] in kinds),'other')
        item['id']=old.id if old else str(uuid.uuid5(uuid.UUID(r.id),item['source_key']))
        # Only images structurally nested inside this activity's own list item
        # can be assigned. Unscoped gallery images are never guessed.
        authored=lines[row['line']-1] if row['line']<=len(lines) else ''
        bullet=re.match(r'^( *)(?:[-*+]|\d+[.)])\s',authored)
        if bullet:
            base=len(bullet[1]);end=len(lines)+1
            for index in range(row['line'],len(lines)):
                line=lines[index]
                if re.match(r'^\s*#{1,6}\s',line) or re.match(r'^( *)(?:[-*+]|\d+[.)])\s',line) and len(line)-len(line.lstrip(' '))<=base:
                    end=index+1;break
            item['media_ids']=list(dict.fromkeys(attrs['id'] for number,attrs in media if row['line']<number<end and len(lines[number-1])-len(lines[number-1].lstrip(' '))>base))
        if old:
            before={'day':old.day.isoformat(),'time':old.time,'title':old.title,'description':old.description,'place_id':old.place_id,'kind':old.kind}
            previous_media=next((a['media_ids'] for a in life['activities'] if a['id']==old.id),[])
            differs=any(item[k]!=value for k,value in before.items()) or set(item['media_ids'])!=set(previous_media)
            if not old.markdown_owned:
                if differs:conflicts.append({'id':old.id,'title':old.title,'message':'正文与人工维护的活动不同，保留人工版本，不自动覆盖'})
                continue
            order.append(old.id)
            if differs:changes.append({'operation':'update','item':item})
            continue
        # Inactive historical source identities are retained; don't resurrect
        # a user-removed activity just because its text still exists.
        historical=db.get(TripActivity,item['id'])
        if historical:continue
        order.append(item['id']);changes.append({'operation':'add','item':item})
    for activity in existing:
        if activity.markdown_owned and activity.source_key and activity.source_key not in seen:
            changes.append({'operation':'remove','item':{'id':activity.id,'title':activity.title,'day':activity.day.isoformat(),'source_key':activity.source_key}})
    current_order=[a['id'] for a in life['activities'] if any(row.id==a['id'] and row.markdown_owned for row in existing)]
    if [id for id in order if id in current_order]!=[id for id in current_order if id in order]:
        changes.append({'operation':'reorder','item':{'id':r.id,'title':'按正文顺序调整自动活动','day':''}})
    manual=[{'id':a.id,'title':a.title,'day':a.day.isoformat()} for a in existing if not a.markdown_owned or not a.source_key]
    return {'body_hash':fingerprint(r.body),'revision':r.revision,'changes':changes,'preserved':manual,'conflicts':conflicts,'order':order,'warnings':result['warnings']}


def apply(db,r,data,actor,*,automatic=False):
    from ..content_schemas import RecordUpdate
    from .content import record_data,apply_record_update
    preview=proposal(db,r)
    if data['expected_revision']!=r.revision or data['body_hash']!=preview['body_hash']:
        raise HTTPException(409,'正文或行程已更新，请重新预览差异；当前编辑内容保留')
    if not preview['changes']:
        record_audit(db,r,'needs_review' if preview['warnings'] else 'generated')
        db.flush();return r
    owned={a.id for a in db.scalars(select(TripActivity).where(TripActivity.record_id==r.id,TripActivity.markdown_owned.is_(True),TripActivity.source_key.is_not(None),TripActivity.active.is_(True)))}
    current=record_data(db,r);life=copy.deepcopy(current['life'])
    removed={change['item']['id'] for change in preview['changes'] if change['operation']=='remove'}
    life['activities']=[a for a in life['activities'] if a['id'] not in removed]
    added=[change['item'] for change in preview['changes'] if change['operation']=='add']
    updates={c['item']['id']:c['item'] for c in preview['changes'] if c['operation']=='update'}
    life['activities']=[{**a,**updates.get(a['id'],{})} for a in life['activities']]
    life['activities'].extend(added)
    by_id={a['id']:a for a in life['activities']};ordered=iter(by_id[id] for id in preview['order'] if id in by_id)
    auto_ids=owned|{a['id'] for a in added}
    life['activities']=[next(ordered) if a['id'] in auto_ids else a for a in life['activities']]
    if len(life['activities'])>300:raise HTTPException(422,'提取后超过300项活动，请先整理现有行程')
    payload={k:current[k] for k in ('schema_version','title','body','body_format','summary','display_date','status','values','tag_ids')}
    payload['connections']={'media':[{'id':m['id'],'cover':m['cover'],'caption':m['caption']} for m in current['connections']['media']], 'places':[p['id'] for p in current['connections']['places']], 'links':[{'id':link['id'],'label':link['label']} for link in current['connections']['links']]}
    payload.update(expected_revision=r.revision,life=life)
    def before_snapshot(updated):
        for id in owned|{item['id'] for item in added}:
            activity=db.get(TripActivity,id)
            if activity and activity.active:activity.markdown_owned=True
        record_audit(db,updated,'needs_review' if automatic and added or preview['warnings'] else 'generated')
    updated=apply_record_update(db,r,RecordUpdate.model_validate(payload),actor,before_snapshot=before_snapshot)
    return updated


def after_publish(db,r,actor,previous_status):
    from .experiences import options
    if not options(db,r)["travel_enabled"]:return r
    """Called AFTER article commit. Extraction failure cannot undo publication."""
    if r.status!='published' or previous_status=='published':return r
    if db.get(ResourceReferenceAudit,audit_key(r.id)):return r
    plan=db.get(TripPlan,r.id)
    from .templates import binding_data
    from .content import fields_for
    binding=binding_data(db,r)
    travel=bool(plan and plan.start_date) or bool(binding and any(module['kind']=='itinerary' for module in binding['config']['modules'])) or any(field['active'] and field['kind']=='date' and field['name'] in ('出发日期','旅行开始日期') for field in fields_for(db,r.type_id,r.schema_version))
    if not travel:return r
    expected=r.revision;id=r.id
    try:
        from .archive import write_lock
        from .content import get_record
        write_lock(db);db.expire_all();current=get_record(db,id)
        if current.revision!=expected:raise HTTPException(409,'文章已经更新，请手动重新提取')
        preview=proposal(db,current)
        # First publication only adds. Any old managed rows require explicit
        # diff confirmation rather than implicit deletion.
        if any(c['operation']=='remove' for c in preview['changes']):
            record_audit(db,current,'needs_review','已有历史行程，请先预览差异再同步');db.commit();return current
        current=apply(db,current,{'expected_revision':expected,'body_hash':preview['body_hash']},actor,automatic=True)
        db.commit();return current
    except Exception:
        db.rollback()
        # Fixed public diagnostic: don't expose SQL, paths, or private text.
        from .archive import write_lock
        from .content import get_record
        write_lock(db);current=get_record(db,id)
        if current.revision==expected:
            record_audit(db,current,'failed','文章已发布，行程提取失败；原行程保留，请检查出发日期和正文后重试')
            db.commit()
        return current
