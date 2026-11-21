"""Logical-only organization. Archive write lock precedes all row modifications."""
import uuid
from datetime import timedelta,timezone
from sqlalchemy import select
from fastapi import HTTPException
from ..models import now
from ..archive_models import MediaFolder,MediaAsset
from ..v5_models import RecordMediaFolder,MediaArchiveRule,MediaArchivePlan
from .folders import validate_tree,require_folder
from .archive import write_lock,asset,asset_data

def article_folder(db,record):
    binding=db.get(RecordMediaFolder,record.id)
    if binding:return binding.folder_id
    base=record.title.strip()[:85] or '未命名文章'
    name=base
    existing=set(db.scalars(select(MediaFolder.normalized_name).where(MediaFolder.parent_id.is_(None))))
    import unicodedata
    counter=1
    while unicodedata.normalize('NFKC',name).casefold() in existing:
        suffix=' · '+record.id[:8]+('' if counter==1 else '-'+str(counter))
        name=base[:100-len(suffix)]+suffix;counter+=1
        if counter>1000:raise HTTPException(409,'同名文件夹过多，请明确整理后重试')
    id=str(uuid.uuid4())
    normalized=validate_tree(db,id,None,name)
    db.add(MediaFolder(id=id,name=name,normalized_name=normalized,parent_id=None));db.flush()
    db.add(RecordMediaFolder(record_id=record.id,folder_id=id));db.flush();return id

def path_for(rule,media):
    timestamp=media.created_at if media.created_at.tzinfo else media.created_at.replace(tzinfo=timezone.utc)
    uploaded=timestamp.astimezone(timezone.utc).date()
    day=media.captured_on if rule.date_source=='captured' else uploaded
    if not day and rule.fallback=='uploaded':day=uploaded
    parts=[str(day.year)] if day else ['拍摄日期未知']
    if day and rule.granularity in {'month','day'}:parts.append(f'{day.month:02}')
    if day and rule.granularity=='day':parts.append(f'{day.day:02}')
    if rule.by_type:parts.append({'image/jpeg':'JPEG','image/png':'PNG','image/webp':'WebP'}.get(media.mime_type,'其他文件'))
    return parts

def folder_path(db,parent,parts):
    for name in parts:
        rows=list(db.scalars(select(MediaFolder).where(MediaFolder.parent_id==parent)))
        found=next((r for r in rows if r.name==name),None)
        if found:parent=found.id;continue
        id=str(uuid.uuid4());norm=validate_tree(db,id,parent,name)
        db.add(MediaFolder(id=id,name=name,normalized_name=norm,parent_id=parent));db.flush();parent=id
    return parent

def preview(db,rule,items,actor):
    require_folder(db,rule.parent_id)
    result=[]
    for item in items:
        m=asset(db,item.id)
        if m.revision!=item.expected_revision:raise HTTPException(409,'图片已更新，请重新预览')
        result.append({'id':m.id,'revision':m.revision,'folder_id':m.folder_id,'path':path_for(rule,m),'filename':m.filename})
    row=MediaArchivePlan(id=str(uuid.uuid4()),rule_id=rule.id,rule_revision=rule.revision,actor_id=actor,items=result)
    db.add(row);db.flush();return row

def execute(db,plan,actor):
    write_lock(db)
    if plan.actor_id!=actor:raise HTTPException(403,'归档预览不属于当前管理员')
    if plan.completed:return {'id':plan.id,'state':'completed','count':len(plan.items),'replayed':True}
    created=plan.created_at if plan.created_at.tzinfo else plan.created_at.replace(tzinfo=timezone.utc)
    if now()-created>timedelta(hours=24):raise HTTPException(409,'预览已过期，请重新预览')
    rule=db.get(MediaArchiveRule,plan.rule_id)
    if rule.revision!=plan.rule_revision:raise HTTPException(409,'规则已修改，请重新预览')
    for item in plan.items:
        m=asset(db,item['id'])
        if m.revision!=item['revision'] or m.folder_id!=item['folder_id']:raise HTTPException(409,'预览后图片已修改，整批未执行')
    for item in plan.items:
        m=asset(db,item['id']);m.folder_id=folder_path(db,rule.parent_id,item['path']);m.revision+=1
    plan.completed=True;db.flush()
    return {'id':plan.id,'state':'completed','count':len(plan.items),'replayed':False}

def auto_upload(db,media):
    # Deterministic priority. Enabled rules affect NEW unfiled uploads only.
    rule=db.scalar(select(MediaArchiveRule).where(MediaArchiveRule.enabled.is_(True)).order_by(MediaArchiveRule.id).limit(1))
    if rule and media.folder_id is None:media.folder_id=folder_path(db,rule.parent_id,path_for(rule,media))

def adopt_uploads(db,record,ids,actor):
    from ..archive_models import RecordMedia
    from ..content_models import RevisionMediaRef
    if not ids:return
    target=article_folder(db,record)
    for id in ids:
        m=asset(db,id)
        if m.uploaded_by!=actor:raise HTTPException(403,'不能自动归档其他用户上传的资源')
        created=m.created_at if m.created_at.tzinfo else m.created_at.replace(tzinfo=timezone.utc)
        if now()-created>timedelta(hours=24):raise HTTPException(409,'上传归档意图已过期；请选择已有资源，不会移动历史图片')
        shared=db.scalar(select(RecordMedia.record_id).where(RecordMedia.media_id==m.id,RecordMedia.record_id!=record.id).limit(1))
        historical=db.scalar(select(RevisionMediaRef.record_id).where(RevisionMediaRef.media_id==m.id,RevisionMediaRef.record_id!=record.id).limit(1))
        if shared or historical:continue
        if m.folder_id!=target:m.folder_id=target;m.revision+=1
