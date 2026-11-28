"""Complete, conservative resource usage and an internal audit gate."""
import re,uuid
from sqlalchemy import select
from fastapi import HTTPException
from markdown_it import MarkdownIt
from ..archive_models import RecordMedia,RecordPlace,MediaAsset,ResourceReferenceAudit
from ..content_models import ContentRecord,RecordBodyMedia,RevisionMediaRef,RecordRevision
from ..life_models import ActivityMedia,TripActivity,PhotoAnnotation
from ..blog_models import Section,SiteConfig

_PRIVATE=re.compile(r'(?:/api)?/library-media/([0-9a-fA-F-]{36})/(?:preview|thumbnail|original)(?:$|[?#\s\"\'])')
def markdown_media_ids(source):
    ids=set()
    def extract(value):
        for m in _PRIVATE.finditer(value):
            try:ids.add(str(uuid.UUID(m[1])))
            except ValueError:pass
    for t in MarkdownIt().parse(source):
        if t.type=='html_block':extract(t.content)
        for c in t.children or []:
            if c.type in ('image','link_open'):extract(c.attrGet('src') or c.attrGet('href') or '')
            elif c.type=='html_inline':extract(c.content)
    return ids

def snapshot_media_ids(snapshot):
    from .body_media import referenced_ids
    ids=referenced_ids(snapshot)
    ids |= markdown_media_ids(snapshot.get('body',''))
    for f in snapshot.get('fields',[]):
        value=snapshot.get('values',{}).get(f.get('id'))
        if f.get('kind')=='markdown' and isinstance(value,str):ids |= markdown_media_ids(value)
    return ids

CATEGORIES = ('current', 'history', 'inactive', 'trash', 'system')

def reference(record, kind, *, active=True, history=False, **extra):
    category = 'history' if history else ('trash' if record and record.deleted_at else ('current' if active else 'inactive'))
    return {'id': record.id if record else extra.pop('record_id', ''),
            'title': record.title if record else '来源文章不存在',
            'deleted': bool(record and record.deleted_at), 'active': bool(active and not history and record and not record.deleted_at),
            'type_id': record.type_id if record else '', 'kind': kind, 'category': category, 'historical': bool(history), **extra}

def usage_summary(rows):
    # Count distinct articles, revisions or system identities within each category.
    return {category: len({(r['id'], r.get('revision')) for r in rows if r['category'] == category}) for category in CATEGORIES}

def media_usage(db,id):
    from ..experience_models import ExperienceMedia, Experience
    results=[]
    source_cache={}
    def source_ids(record):
        if record.id not in source_cache:
            from .content import fields_for
            source_cache[record.id]=snapshot_media_ids({'body':record.body,'body_format':record.body_format,'values':record.values,'fields':fields_for(db,record.type_id,record.schema_version)})
        return source_cache[record.id]
    def add(query,kind):
        for r in db.scalars(query).unique():results.append(reference(r,kind))
    add(select(ContentRecord).join(RecordMedia,RecordMedia.record_id==ContentRecord.id).where(RecordMedia.media_id==id),'画廊/封面')
    for record in db.scalars(select(ContentRecord).join(RecordBodyMedia,RecordBodyMedia.record_id==ContentRecord.id).where(RecordBodyMedia.media_id==id)):
        results.append(reference(record,'正文',active=id in source_ids(record)))
    for a, ref in db.execute(select(TripActivity,ActivityMedia).join(ActivityMedia,ActivityMedia.activity_id==TripActivity.id).where(ActivityMedia.media_id==id)):
        results.append(reference(db.get(ContentRecord,a.record_id),'行程',active=a.active and ref.active,source_id=a.id))
    for p in db.scalars(select(PhotoAnnotation).where(PhotoAnnotation.media_id==id)):
        results.append(reference(db.get(ContentRecord,p.record_id),'照片注记',active=p.active))
    for ref,e in db.execute(select(ExperienceMedia,Experience).join(Experience,(Experience.record_id==ExperienceMedia.record_id)&(Experience.id==ExperienceMedia.entry_id)).where(ExperienceMedia.media_id==id)):
        record=db.get(ContentRecord,ref.record_id)
        from .experiences import entries
        present=any(item['id']==e.id and id in item['media_ids'] for item in entries(record.body)) if record and record.body_format==2 else False
        results.append(reference(record,'卡片图片',active=ref.active and e.active and present,source_id=e.id))
    for ref in db.scalars(select(RevisionMediaRef).where(RevisionMediaRef.media_id==id)):
        results.append(reference(db.get(ContentRecord,ref.record_id),'历史修订',history=True,revision=ref.number))
    # Protection never depends exclusively on the correctness of derived edges.
    for record in db.scalars(select(ContentRecord)):
        if id in source_ids(record) and not any(r['id']==record.id and r['kind']=='正文' and r['active'] for r in results):
            results.append(reference(record,'当前正文来源'))
    protected={(r['id'],r.get('revision')) for r in results if r['category']=='history'}
    for revision in db.scalars(select(RecordRevision)):
        if (revision.record_id,revision.number) not in protected and id in snapshot_media_ids(revision.snapshot):
            results.append(reference(db.get(ContentRecord,revision.record_id),'历史修订（待补齐保护索引）',history=True,revision=revision.number))
    for section in db.scalars(select(Section).where(Section.cover_id==id)):
        results.append({'id':section.id,'title':section.name,'kind':'栏目封面','category':'system','active':False})
    from ..album_models import Album, AlbumPhoto
    for album in db.scalars(select(Album).outerjoin(AlbumPhoto,AlbumPhoto.album_id==Album.id).where((AlbumPhoto.media_id==id)|(Album.cover_id==id)).distinct()):
        results.append({'id':album.id,'title':album.name,'kind':'手工相册','category':'system','active':False})
    return results

def assert_media_unused(db,id):
    usage=media_usage(db,id)
    if usage:raise HTTPException(409,{'message':'图片仍被当前或历史内容引用，不能删除','references':usage})

def require_audit(db):
    row=db.get(ResourceReferenceAudit,'media')
    if row is None or row.value.get('media_version')!=1 or row.value.get('issues'):
        raise HTTPException(409,'资源引用审计未完成或存在异常，永久删除保持关闭；请检查升级审计报告')

def audit_media(db):
    """Explicit migration/CLI only. No snapshot rewriting, no filesystem deletion."""
    from ..content_models import RecordRevision
    issues=[]
    for row in db.scalars(select(RecordRevision).execution_options(yield_per=100)):
        try:ids=snapshot_media_ids(row.snapshot)
        except Exception:
            issues.append({'record_id':row.record_id,'revision':row.number,'code':'unknown_snapshot'});continue
        for id in ids:
            if db.get(MediaAsset,id) is None:issues.append({'record_id':row.record_id,'revision':row.number,'code':'missing_media'});continue
            if db.get(RevisionMediaRef,(row.record_id,row.number,id)) is None:db.add(RevisionMediaRef(record_id=row.record_id,number=row.number,media_id=id))
    # Current records may predate revision capture; current Markdown fields count too.
    for r in db.scalars(select(ContentRecord).execution_options(yield_per=100)):
        from .content import fields_for
        try:ids=snapshot_media_ids({'body':r.body,'body_format':r.body_format,'fields':fields_for(db,r.type_id,r.schema_version),'values':r.values})
        except Exception:issues.append({'record_id':r.id,'code':'unknown_current_body'});continue
        for id in ids:
            if db.get(MediaAsset,id) is None:issues.append({'record_id':r.id,'code':'missing_current_media'});continue
            if db.get(RecordBodyMedia,(r.id,id)) is None:db.add(RecordBodyMedia(record_id=r.id,media_id=id))
    row=db.get(ResourceReferenceAudit,'media')
    value={'media_version':1,'issues':issues}
    if row:row.value={**row.value,**value}
    else:db.add(ResourceReferenceAudit(key='media',value=value))
    db.flush();return value

if __name__=='__main__':
    import json
    from ..db import SessionLocal
    from ..migrations import require_current_schema
    from .write_barrier import writer
    from .archive import write_lock
    with SessionLocal() as db,writer(db.bind):
        require_current_schema(db.bind);write_lock(db)
        from .places import audit as audit_places
        result={'media':audit_media(db),'places':audit_places(db)};db.commit()
    print(json.dumps(result,ensure_ascii=False))  # IDs and diagnostic codes only
