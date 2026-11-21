"""Readable Markdown marks with explicit place identities; called inside record transaction."""
import uuid,hashlib
from sqlalchemy import select,delete,func
from fastapi import HTTPException
from ..archive_models import Place,RecordPlace,RecordMarkedPlace,PlaceAlias
from .places import norm,canonical
from .markdown_marks import parse,document

KINDS={'l':'地点','f':'餐厅','s':'景点','h':'住宿','t':'交通','c':'咖啡','p':'购物'}
CATEGORIES={'l':{'','地点','地区','城市','region','city'},'f':{'餐厅','美食','restaurant','food'},'s':{'景点','sight'},'h':{'住宿','酒店','hotel'},'t':{'交通','transport'},'c':{'咖啡','饮品','cafe'},'p':{'购物','shopping'}}

def find_existing(mark,catalog,aliases,deleted_names,address=''):
    """Read-only half of the existing resolver; shared by save and preview."""
    region_key=mark['region']
    if any(d.get('name')==norm(mark['name']) and (not region_key or not (d.get('city') or d.get('region')) or norm(region_key) in {d.get('city'),d.get('region')}) for d in deleted_names):raise HTTPException(422,'地点已从库中删除，不允许旧标记自动复活；请在地点管理明确创建新身份并通过补全选择UUID')
    named=[row for row in catalog.get(norm(mark['name']),[]) if row.id not in aliases and norm(row.category) in CATEGORIES[mark['kind']]]
    candidates=[row for row in named if (not region_key or norm(region_key) in {norm(row.region),norm(row.city)}) and (not address or norm(row.address)==norm(address))]
    if len(candidates)>1:raise HTTPException(422,'同名地点不明确，请通过 @ 补全选择具体地点：'+mark['name'])
    return candidates[0] if candidates else None


def document_marks(body):
    return parse(body).marks


def key(mark,region):return hashlib.sha256((mark['kind']+'|'+norm(region)+'|'+norm(mark['name'])+'|'+str(mark.get('place_id') or '')).encode()).hexdigest()


def sync(db,record):
    previous={x.source_key:x.place_id for x in db.scalars(select(RecordMarkedPlace).where(RecordMarkedPlace.record_id==record.id))}
    resolved={};bindings={};cache={};catalog=None;aliases=None;deleted_names=None
    associated=set(db.scalars(select(RecordPlace.place_id).where(RecordPlace.record_id==record.id)))
    for mark in document(db,record).marks:
        region_key=mark['region']
        identity=key(mark,region_key)
        p=cache.get(identity)
        if p is None:
            pid=mark['place_id'] or previous.get(identity)
            if pid:
                p=db.get(Place,canonical(db,pid))
                if not p or (not p.active and identity not in previous):raise HTTPException(422,'标记地点不存在或已停用，请重新选择')
            else:
                # One catalog read per transaction; repeated prose marks do not
                # produce N+1 catalog/alias queries or repeated resource writes.
                if catalog is None:
                    catalog={}
                    for row in db.scalars(select(Place).where(Place.active.is_(True))):catalog.setdefault(norm(row.name),[]).append(row)
                    aliases=set(db.scalars(select(PlaceAlias.source_id)))
                from ..archive_models import ResourceReferenceAudit
                if deleted_names is None:deleted_names=[r.value for r in db.scalars(select(ResourceReferenceAudit).where(ResourceReferenceAudit.key.like('dp:%')))]
                p=find_existing(mark,catalog,aliases,deleted_names)
                if p is None:
                    p=Place(id=str(uuid.uuid4()),name=mark['name'],category=KINDS[mark['kind']],region=region_key,country='',city='',address='',notes='',active=True,revision=1)
                    db.add(p);db.flush();catalog.setdefault(norm(p.name),[]).append(p)
            cache[identity]=p
        bindings[identity]=p.id;resolved[(mark['kind'],mark['name'],region_key,mark.get('place_id'))]=p.id
        if p.id not in associated:
            if len(associated)>=100:raise HTTPException(422,'单篇文章最多关联100个地点，请减少标记或整理历史关联')
            db.add(RecordPlace(record_id=record.id,place_id=p.id,markdown_owned=True));associated.add(p.id);db.flush()
    from .experiences import entries
    for entry in entries(record.body) if record.body_format==2 else []:
        pid=entry['fields'].get('place_id')
        if pid:
            pid=canonical(db,pid);p=db.get(Place,pid)
            if not p or not p.active:raise HTTPException(422,'卡片关联地点不存在或已停用')
            bindings['entry:'+entry['id']]=pid
            if pid not in associated:
                if len(associated)>=100:raise HTTPException(422,'单篇最多关联100个地点')
                db.add(RecordPlace(record_id=record.id,place_id=pid,markdown_owned=True));associated.add(pid)
    db.execute(delete(RecordMarkedPlace).where(RecordMarkedPlace.record_id==record.id))
    db.add_all(RecordMarkedPlace(record_id=record.id,source_key=k,place_id=p) for k,p in bindings.items())
    db.flush()
    return resolved


def sync_activities(db,record,plan,places):
    if not plan.start_date:return  # Plain articles do not acquire a travel plan.
    from .itinerary import extract
    from ..life_models import TripActivity,ActivityMedia
    rows=list(db.scalars(select(TripActivity).where(TripActivity.record_id==record.id)))
    previous={x.source_key:x for x in rows if x.source_key}
    bindings={x.source_key:x.place_id for x in db.scalars(select(RecordMarkedPlace).where(RecordMarkedPlace.record_id==record.id))}
    for row in rows:
        if row.markdown_owned:row.active=False
    parsed=document(db,record)
    position=max([x.position for x in rows if not x.markdown_owned and x.active]+[-1])+1
    for item in extract(record.body,plan.start_date,plan.end_date)['items']:
        found=[m for m in parsed.marks if m['line']==item['line']]
        if not found:continue
        pid=None
        for mark in found:
            bound=bindings.get(key(mark,mark['region']))
            if not bound:raise HTTPException(422,'正文标记缺少地点绑定，请重新保存正文；不会猜测地点身份')
            pid=bound
        row=previous.get(item['source_key'])
        if row and not row.markdown_owned:continue  # Old/manual imports never overwritten.
        if not row:
            if position>=300:raise HTTPException(422,'行程超过300项，请减少正文标记活动')
            row=TripActivity(id=str(uuid.uuid5(uuid.UUID(record.id),item['source_key'])),record_id=record.id,markdown_owned=True)
            db.add(row);rows.append(row)
        from datetime import date
        row.day=date.fromisoformat(item['day']);row.time=item['time'];row.title=' · '.join(m['name'] for m in found)[:200]
        row.description=item['description'];row.source_key=item['source_key'];row.position=position;row.active=True;row.place_id=pid
        row.kind='food' if any(m['kind'] in ('f','c') for m in found) else 'sight' if any(m['kind']=='s' for m in found) else 'transport' if any(m['kind']=='t' for m in found) else 'other'
        position+=1
        if position>300:raise HTTPException(422,'行程超过300项，请减少正文标记活动')


def prune_connections(db,record):
    """Only derived links may expire; entities, manual links and history stay."""
    from ..life_models import TripActivity,PhotoAnnotation
    keep=set(db.scalars(select(RecordMarkedPlace.place_id).where(RecordMarkedPlace.record_id==record.id)))
    keep.update(db.scalars(select(TripActivity.place_id).where(TripActivity.record_id==record.id,TripActivity.active.is_(True),TripActivity.place_id.is_not(None))))
    keep.update(db.scalars(select(PhotoAnnotation.place_id).where(PhotoAnnotation.record_id==record.id,PhotoAnnotation.active.is_(True),PhotoAnnotation.place_id.is_not(None))))
    for ref in db.scalars(select(RecordPlace).where(RecordPlace.record_id==record.id,RecordPlace.markdown_owned.is_(True))):
        if ref.place_id not in keep:db.delete(ref)
    db.flush()
