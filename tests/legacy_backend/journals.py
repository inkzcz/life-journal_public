from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_, delete
from sqlalchemy.orm import Session as DBSession, defer
from app.dependencies import db_dep, current_user, require_admin, get_settings
from app.models import User, Journal, JournalMetadata, JournalTag, Media
from .schemas import JournalIn
from .service import serialize, serialize_many, save_metadata, get_journal

from app.services.archive import write_lock

router = APIRouter()

@router.get('/api/journals')
def list_journals(db:DBSession=Depends(db_dep),user:User=Depends(current_user)):
    return serialize_many(db.scalars(select(Journal).order_by(Journal.updated_at.desc(),Journal.id.desc())).all(),db)

@router.get('/api/journals/page')
def page_journals(
    page:int=Query(default=1,ge=1), page_size:int=Query(default=20,ge=1,le=100),
    q:str=Query(default='',max_length=200), date_from:date | None=None,
    date_to:date | None=None, category:str=Query(default='',max_length=80),
    tag:str=Query(default='',max_length=40),
    db:DBSession=Depends(db_dep), user:User=Depends(current_user),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422,'开始日期不能晚于结束日期')
    # Legacy records retain their stored timestamps; date fallback is computed only on read.
    if db.bind.dialect.name == 'sqlite':
        legacy_date = func.date(Journal.created_at, '+8 hours')
    else:
        legacy_date = func.date(func.timezone('Asia/Shanghai', Journal.created_at))
    entry_date = func.coalesce(JournalMetadata.entry_date, legacy_date)
    query = select(Journal).options(defer(Journal.content)).outerjoin(JournalMetadata)
    if q.strip():
        query = query.where(or_(Journal.title.icontains(q.strip(),autoescape=True), Journal.content.icontains(q.strip(),autoescape=True)))
    if date_from:
        query = query.where(entry_date >= date_from)
    if date_to:
        query = query.where(entry_date <= date_to)
    if category.strip():
        query = query.where(JournalMetadata.category == category.strip())
    if tag.strip():
        query = query.where(select(JournalTag.journal_id).where(JournalTag.journal_id==Journal.id,JournalTag.name==tag.strip()).exists())
    total = db.scalar(query.with_only_columns(func.count(),maintain_column_froms=True))
    items = db.scalars(query.order_by(entry_date.desc(),Journal.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {'items':serialize_many(items,db,include_content=False), 'total':total, 'page':page, 'page_size':page_size}


@router.get('/api/journals/filters')
def journal_filters(db:DBSession=Depends(db_dep),user:User=Depends(current_user)):
    return {
        'categories':list(db.scalars(select(JournalMetadata.category).where(JournalMetadata.category!='').distinct().order_by(JournalMetadata.category))),
        'tags':list(db.scalars(select(JournalTag.name).distinct().order_by(JournalTag.name))),
    }


@router.post('/api/journals')
def create_journal(data:JournalIn,db:DBSession=Depends(db_dep),user:User=Depends(require_admin)):
    write_lock(db)
    j=Journal(title=data.title.strip(),content=data.content)
    if not j.title:raise HTTPException(422,'标题不能为空')
    db.add(j);db.flush();save_metadata(j,data,db,creating=True)
    db.commit();db.refresh(j);return serialize(j,db)

@router.get('/api/journals/{id}')
def read_journal(id:int,db:DBSession=Depends(db_dep),user:User=Depends(current_user)):
    return serialize(get_journal(id,db),db)

@router.put('/api/journals/{id}')
def update_journal(id:int,data:JournalIn,db:DBSession=Depends(db_dep),user:User=Depends(require_admin)):
    write_lock(db)
    j=get_journal(id,db)
    if not data.title.strip():raise HTTPException(422,'标题不能为空')
    j.title=data.title.strip();j.content=data.content;j.updated_at=datetime.now(timezone.utc)
    save_metadata(j,data,db)
    db.commit();db.refresh(j);return serialize(j,db)

@router.delete('/api/journals/{id}')
def delete_journal(id:int,db:DBSession=Depends(db_dep),user:User=Depends(require_admin),settings=Depends(get_settings)):
    write_lock(db)
    j=get_journal(id,db)
    media = db.scalars(select(Media).where(Media.journal_id==id)).all()
    paths = [p for m in media for p in [settings.media_dir/m.id,settings.media_dir/'legacy-previews-v1'/(m.id+'.webp')]]
    for m in media:
        db.delete(m)
    db.execute(delete(JournalTag).where(JournalTag.journal_id==id))
    db.execute(delete(JournalMetadata).where(JournalMetadata.journal_id==id))
    db.flush()  # Delete children before the PostgreSQL ON DELETE CASCADE.
    db.delete(j)
    db.commit()
    # Keep files intact if the database transaction fails.
    for path in paths:
        path.unlink(missing_ok=True)
    return {'ok':True}
