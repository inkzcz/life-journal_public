"""One transaction/lock order: archive write lock, then tag/record writes."""
import unicodedata
import uuid
from fastapi import HTTPException
from sqlalchemy import select, delete, func
from ..tag_models import Tag,RecordTag,JournalTagIdentity
from ..models import JournalTag,now
from ..content_models import ContentRecord
from .archive import write_lock


def normalize(name):
    display=name.strip()
    key=' '.join(unicodedata.normalize('NFKC',display).split()).casefold()
    if not display or len(display)>40 or len(key)>160 or any(unicodedata.category(c).startswith('C') for c in display):
        raise HTTPException(422,'标签需要1～40个可见字符，不接受控制字符')
    return display,key


def identity(db,name):
    display,key=normalize(name)
    tag=db.scalar(select(Tag).where(Tag.normalized_name==key))
    if tag:
        tag=resolve(db,tag.id)
        if tag.deleted_at:raise HTTPException(409,'标签已全局删除，不会因同名请求重新启用；请使用新的名称')
        return tag
    tag=Tag(id=str(uuid.uuid4()),name=display,normalized_name=key)
    db.add(tag);db.flush();return tag


def resolve(db,id):
    seen=set()
    while id not in seen:
        seen.add(id);t=db.get(Tag,str(id))
        if not t:raise HTTPException(422,'标签不存在')
        if not t.merged_into:return t
        id=t.merged_into
    raise HTTPException(409,'标签合并链异常，操作已停止')


def active_tag(db,id):
    t=db.get(Tag,str(id))
    if not t or t.deleted_at or t.merged_into:raise HTTPException(409,'标签已删除或合并，请重新选择')
    return t


def record_tags(db,ids):
    result={}
    if ids:
        for rid,id,name in db.execute(select(RecordTag.record_id,Tag.id,Tag.name).join(Tag,RecordTag.tag_id==Tag.id).where(RecordTag.record_id.in_(ids)).order_by(Tag.normalized_name,Tag.id)):
            result.setdefault(rid,[]).append({'id':id,'name':name})
    return result


def replace_tags(db,r,ids,historical=False):
    if ids is None:return  # old clients and pre-0009 snapshots preserve associations
    write_lock(db)
    if len(ids)>10 or len(set(map(str,ids)))!=len(ids):raise HTTPException(422,'最多10个标签，不能重复')
    targets=[]
    for id in ids:
        t=resolve(db,str(id)) if historical else active_tag(db,id)
        if t.deleted_at:
            if historical:continue
            else:raise HTTPException(409,'标签已删除')
        if t.id not in targets:targets.append(t.id)
    db.execute(delete(RecordTag).where(RecordTag.record_id==r.id))
    db.add_all(RecordTag(record_id=r.id,tag_id=id) for id in targets);db.flush()


def sync_journal(db,jid,previous=None):
    write_lock(db);db.flush()
    db.execute(delete(JournalTagIdentity).where(JournalTagIdentity.journal_id==jid))
    for name in db.scalars(select(JournalTag.name).where(JournalTag.journal_id==jid)):
        t=resolve(db,previous[name]) if previous and name in previous else identity(db,name)
        db.add(JournalTagIdentity(journal_id=jid,name=name,tag_id=t.id))
    db.flush()


def counts(db,id):
    return {'records':db.scalar(select(func.count()).select_from(RecordTag).where(RecordTag.tag_id==id)),
            'journals':db.scalar(select(func.count(func.distinct(JournalTagIdentity.journal_id))).where(JournalTagIdentity.tag_id==id))}


def merge(db,source,target,actor):
    write_lock(db)
    a=active_tag(db,source);b=active_tag(db,target)
    if a.id==b.id:raise HTTPException(422,'不能合并到自身')
    from .content import revision_snapshot
    ids=list(db.scalars(select(RecordTag.record_id).where(RecordTag.tag_id==a.id)))
    for rid in ids:
        if not db.get(RecordTag,(rid,b.id)):db.add(RecordTag(record_id=rid,tag_id=b.id))
    db.execute(delete(RecordTag).where(RecordTag.tag_id==a.id))
    for row in db.scalars(select(JournalTagIdentity).where(JournalTagIdentity.tag_id==a.id)):row.tag_id=b.id
    a.merged_into=b.id;a.updated_at=now();db.flush()
    # A stale editor must not silently undo a catalog merge.
    for r in db.scalars(select(ContentRecord).where(ContentRecord.id.in_(ids)).order_by(ContentRecord.id)):
        r.revision+=1;r.updated_at=now();db.flush();revision_snapshot(db,r,actor)
    return {'records':len(ids),'target_id':b.id}
