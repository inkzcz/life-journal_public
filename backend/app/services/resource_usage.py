"""Complete, conservative resource usage and an internal audit gate."""
import re,uuid
from sqlalchemy import select
from fastapi import HTTPException
from markdown_it import MarkdownIt
from ..archive_models import RecordMedia,RecordPlace,MediaAsset,ResourceReferenceAudit
from ..content_models import ContentRecord,RecordBodyMedia,RevisionMediaRef
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

def media_usage(db,id):
    results=[]
    def add(query,kind):
        for r in db.scalars(query):results.append({'id':r.id,'title':r.title,'deleted':bool(r.deleted_at),'type_id':r.type_id,'kind':kind})
    add(select(ContentRecord).join(RecordMedia,RecordMedia.record_id==ContentRecord.id).where(RecordMedia.media_id==id),'画廊/封面')
    add(select(ContentRecord).join(RecordBodyMedia,RecordBodyMedia.record_id==ContentRecord.id).where(RecordBodyMedia.media_id==id),'正文')
    add(select(ContentRecord).join(TripActivity,TripActivity.record_id==ContentRecord.id).join(ActivityMedia,ActivityMedia.activity_id==TripActivity.id).where(ActivityMedia.media_id==id).distinct(),'行程（含停用历史）')
    add(select(ContentRecord).join(PhotoAnnotation,PhotoAnnotation.record_id==ContentRecord.id).where(PhotoAnnotation.media_id==id).distinct(),'照片注记（含停用历史）')
    for rid,number,title,deleted in db.execute(select(RevisionMediaRef.record_id,RevisionMediaRef.number,ContentRecord.title,ContentRecord.deleted_at).join(ContentRecord,ContentRecord.id==RevisionMediaRef.record_id).where(RevisionMediaRef.media_id==id)):
        results.append({'id':rid,'title':title,'deleted':bool(deleted),'kind':'历史修订','revision':number})
    for s in db.scalars(select(Section).where(Section.cover_id==id)):results.append({'id':s.id,'title':s.name,'kind':'栏目封面'})
    from ..album_models import Album, AlbumPhoto
    for a in db.scalars(select(Album).outerjoin(AlbumPhoto,AlbumPhoto.album_id==Album.id).where((AlbumPhoto.media_id==id)|(Album.cover_id==id)).distinct()):results.append({'id':a.id,'title':a.name,'kind':'手工相册'})
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
