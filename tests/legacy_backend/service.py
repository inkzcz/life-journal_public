from datetime import timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, delete
from app.models import Journal, JournalMetadata, JournalTag

JOURNAL_ZONE = ZoneInfo('Asia/Shanghai')


def journal_date(j, metadata):
    if metadata:
        return metadata.entry_date
    created = j.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created.astimezone(JOURNAL_ZONE).date()


def serialize_many(journals, db, include_content=True):
    if not journals:
        return []
    ids = [j.id for j in journals]
    metadata = {m.journal_id:m for m in db.scalars(select(JournalMetadata).where(JournalMetadata.journal_id.in_(ids)))}
    tags = {}
    for jid, name in db.execute(select(JournalTag.journal_id,JournalTag.name).where(JournalTag.journal_id.in_(ids)).order_by(JournalTag.name)):
        tags.setdefault(jid, []).append(name)
    result = []
    for j in journals:
        m = metadata.get(j.id)
        item = {
            'id':j.id, 'title':j.title, 'created_at':j.created_at, 'updated_at':j.updated_at,
            'entry_date':journal_date(j,m), 'category':m.category if m else '', 'tags':tags.get(j.id,[]),
        }
        if include_content:
            item['content'] = j.content
        result.append(item)
    return result


def serialize(j, db):
    return serialize_many([j],db)[0]


def save_metadata(j, data, db, creating=False):
    metadata = db.get(JournalMetadata, j.id)
    fields = data.model_fields_set
    if creating or fields & {'entry_date', 'category'}:
        if metadata is None:
            metadata = JournalMetadata(journal_id=j.id, entry_date=journal_date(j, None), category='')
            db.add(metadata)
        if data.entry_date is not None:
            metadata.entry_date = data.entry_date
        if creating or 'category' in fields:
            metadata.category = data.category
    if creating or 'tags' in fields:
        from app.tag_models import JournalTagIdentity
        previous=dict(db.execute(select(JournalTagIdentity.name,JournalTagIdentity.tag_id).where(JournalTagIdentity.journal_id==j.id)).all())
        db.execute(delete(JournalTag).where(JournalTag.journal_id==j.id))
        db.add_all(JournalTag(journal_id=j.id,name=name) for name in data.tags)
        from app.services.tags import sync_journal
        sync_journal(db,j.id,previous)


def get_journal(id:int,db):
    j=db.get(Journal,id)
    if not j: raise HTTPException(404,'日记不存在')
    return j
