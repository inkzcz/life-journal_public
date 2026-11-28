"""Local place identity, immutable history and transactional current-reference merge."""
import unicodedata
from sqlalchemy import select,delete
from fastapi import HTTPException
from ..models import now
from ..archive_models import Place,PlaceAlias,RevisionPlaceRef,RecordPlace,ResourceReferenceAudit,RecordMarkedPlace
from ..content_models import ContentRecord,RecordRevision
from ..life_models import TripActivity,PhotoAnnotation
from .archive import write_lock,place,place_data

def canonical(db,id):
    seen=set()
    while True:
        if id in seen:raise HTTPException(409,'地点别名循环，停止操作')
        seen.add(id);alias=db.get(PlaceAlias,id)
        if not alias:return id
        id=alias.target_id

def snapshot_places(s):
    if not isinstance(s,dict):raise ValueError('snapshot')
    result={str(p['id']) for p in (s.get('connections') or {}).get('places',[])}
    result.update(str(p['place_id']) for p in s.get('marked_places',[]))
    from .experiences import entries
    if s.get('body_format',1)==2:result.update(e['fields']['place_id'] for e in entries(s.get('body','')) if e['fields'].get('place_id'))
    for group in ['activities','photos']:
        result.update(str(p['place_id']) for p in (s.get('life') or {}).get(group,[]) if p.get('place_id'))
    return result

def snapshot_refs(db,id,number,s):
    for pid in snapshot_places(s):
        if db.get(Place,pid) is not None and db.get(RevisionPlaceRef,(id,number,pid)) is None:db.add(RevisionPlaceRef(record_id=id,number=number,place_id=pid))

def audit(db):
    issues=[]
    for row in db.scalars(select(RecordRevision).execution_options(yield_per=100)):
        try:ids=snapshot_places(row.snapshot)
        except Exception:issues.append({'record_id':row.record_id,'revision':row.number,'code':'unknown_snapshot'});continue
        for pid in ids:
            if db.get(Place,pid) is None:issues.append({'record_id':row.record_id,'revision':row.number,'code':'missing_place'})
            elif not db.get(RevisionPlaceRef,(row.record_id,row.number,pid)):db.add(RevisionPlaceRef(record_id=row.record_id,number=row.number,place_id=pid))
    row=db.get(ResourceReferenceAudit,'places');value={'version':1,'issues':issues}
    if row:row.value=value
    else:db.add(ResourceReferenceAudit(key='places',value=value))
    db.flush();return value

def usages(db,id):
    from .resource_usage import reference
    from ..experience_models import Experience
    from ..v5_models import FoodOccurrence
    rows=[]
    from .experiences import entries
    source_cache={}
    def current_entries(record_id):
        if record_id not in source_cache:
            record=db.get(ContentRecord,record_id)
            source_cache[record_id]={e['id']:e for e in entries(record.body)} if record and record.body_format==2 else {}
        return source_cache[record_id]
    for model,column,kind in [(RecordMarkedPlace,RecordMarkedPlace.place_id,'Markdown地点标记'),(RecordPlace,RecordPlace.place_id,'文章地点'),(TripActivity,TripActivity.place_id,'行程'),(PhotoAnnotation,PhotoAnnotation.place_id,'照片注记')]:
        for item in db.scalars(select(model).where(column==id)):
            rows.append(reference(db.get(ContentRecord,item.record_id),kind,active=getattr(item,'active',True)))
    for ref in db.scalars(select(RevisionPlaceRef).where(RevisionPlaceRef.place_id==id)):
        rows.append(reference(db.get(ContentRecord,ref.record_id),'历史修订',history=True,revision=ref.number))
    for alias in db.scalars(select(PlaceAlias).where((PlaceAlias.source_id==id)|(PlaceAlias.target_id==id))):
        rows.append({'id':alias.source_id,'title':'合并身份保留','kind':'地点别名','category':'system','active':False,'target_id':alias.target_id})
    for item in db.scalars(select(FoodOccurrence).where(FoodOccurrence.place_id==id)):
        rows.append(reference(db.get(ContentRecord,item.record_id),'美食索引',active=item.active and (not item.source_key.startswith('entry:') or item.source_key[6:] in current_entries(item.record_id)),source_id=item.id))
    for item in db.scalars(select(Experience)):
        if item.fields.get('place_id')==id:
            rows.append(reference(db.get(ContentRecord,item.record_id),'卡片索引',active=item.active and item.id in current_entries(item.record_id),source_id=item.id))
    # Source is authoritative even if a legacy/missing derived row escaped sync.
    from .experiences import entries
    from .resource_usage import reference
    for record in db.scalars(select(ContentRecord)):
        for entry in entries(record.body) if record.body_format==2 else []:
            if entry['fields'].get('place_id')==id:
                rows.append(reference(record,'正文卡片',source_id=entry['id']))
    protected={(row['id'],row.get('revision')) for row in rows if row['category']=='history'}
    for revision in db.scalars(select(RecordRevision)):
        if (revision.record_id,revision.number) not in protected and id in snapshot_places(revision.snapshot):
            rows.append(reference(db.get(ContentRecord,revision.record_id),'历史修订（待补齐保护索引）',history=True,revision=revision.number))
    return rows

def delete_place(db,id,revision):
    write_lock(db);p=place(db,id)
    if p.revision!=revision:raise HTTPException(409,'地点版本已改变')
    gate=db.get(ResourceReferenceAudit,'places')
    if not gate or gate.value.get('issues') or gate.value.get('version')!=1:raise HTTPException(409,'地点引用审计未完成，禁止删除')
    refs=usages(db,id)
    if not refs:refs=unbound_marker_references(db,p)
    if refs:raise HTTPException(409,{'message':'地点仍被引用，不能删除','references':refs})
    db.add(ResourceReferenceAudit(key='dp:'+p.id,value={'name':norm(p.name),'category':norm(p.category),'region':norm(p.region),'city':norm(p.city)}))
    db.delete(p);db.commit();return {'ok':True}

def norm(s):return unicodedata.normalize('NFKC',s).casefold().strip()
def duplicates(db,id):
    p=place(db,id)
    # Candidates only: identical names with compatible city/country, never automatic.
    return [place_data(x) for x in db.scalars(select(Place).order_by(Place.name,Place.id)) if x.id!=id and not db.get(PlaceAlias,x.id) and norm(x.name)==norm(p.name) and (not x.city or not p.city or norm(x.city)==norm(p.city)) and (not x.country or not p.country or norm(x.country)==norm(p.country))][:100]

def merge(db,id,target,revision,target_revision,actor):
    write_lock(db);p=place(db,id);t=place(db,target)
    if id==target or db.get(PlaceAlias,id) or db.get(PlaceAlias,target) or not t.active:raise HTTPException(409,'请选择两个不同的原始地点，目标必须启用；已有别名不能再次合并')
    if p.revision!=revision or t.revision!=target_revision:raise HTTPException(409,'地点已更新，请重新预览')
    affected=set(db.scalars(select(RecordPlace.record_id).where(RecordPlace.place_id==id)))
    affected.update(db.scalars(select(TripActivity.record_id).where(TripActivity.place_id==id)))
    affected.update(db.scalars(select(PhotoAnnotation.record_id).where(PhotoAnnotation.place_id==id)))
    for ref in list(db.scalars(select(RecordPlace).where(RecordPlace.place_id==id))):
        kept=db.get(RecordPlace,(ref.record_id,target))
        if not kept:db.add(RecordPlace(record_id=ref.record_id,place_id=target,markdown_owned=ref.markdown_owned))
        elif not ref.markdown_owned:kept.markdown_owned=False
        db.delete(ref)
    # Includes inactive references; their old identity is retained in snapshots + alias.
    for model in [TripActivity,PhotoAnnotation,RecordMarkedPlace]:
        for ref in db.scalars(select(model).where(model.place_id==id)):ref.place_id=target
    db.add(PlaceAlias(source_id=id,target_id=target));p.active=False;p.revision+=1;p.updated_at=now();t.revision+=1;t.updated_at=now();db.flush()
    from .content import revision_snapshot
    for rid in sorted(affected):
        r=db.get(ContentRecord,rid);r.revision+=1;r.updated_at=now();db.flush();revision_snapshot(db,r,actor)
    db.commit();return {'source':place_data(p),'target':place_data(t),'affected_records':len(affected),'note':'旧修订不改写；恢复时须明确确认别名映射'}

def unbound_marker_references(db,p):
    """Rare destructive operation: inspect unbound text, never rewrite Markdown."""
    from .marked_places import document_marks,key as mark_key
    def mentions(body,bindings):
        if not isinstance(body,str):return False
        for mark in document_marks(body):
            scope=mark['region']
            target=mark.get('place_id') or bindings.get(mark_key(mark,scope))
            if norm(mark['name'])==norm(p.name) and (not target or canonical(db,target)==p.id):return True
        return False
    result=[]
    for r in db.scalars(select(ContentRecord).execution_options(yield_per=50)):
        bindings={x.source_key:x.place_id for x in db.scalars(select(RecordMarkedPlace).where(RecordMarkedPlace.record_id==r.id))}
        if mentions(r.body,bindings):result.append({'id':r.id,'title':r.title,'kind':'原文同名未绑定标记，需明确地点身份'})
    for revision in db.scalars(select(RecordRevision).execution_options(yield_per=50)):
        s=revision.snapshot
        if mentions(s.get('body',''),{b['source_key']:b['place_id'] for b in s.get('marked_places',[])}):result.append({'id':revision.record_id,'title':s.get('title','历史文章'),'revision':revision.number,'kind':'历史原文标记'})
    return result
