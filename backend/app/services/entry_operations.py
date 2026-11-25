"""Atomic parser-addressed card operations; preserves unrelated article state."""
import hashlib,json,uuid
from fastapi import HTTPException
from sqlalchemy import select,update
from ..content_models import ContentRecord,RecordRevision
from ..models import now
from .archive import write_lock
from .content import get_record,revision_snapshot,get_type
from .experiences import parser,entries,serialize


def locate(body,identity):
    lines=body.splitlines(keepends=True)
    for token in parser().parse(body):
        if token.type=='life_entry' and token.meta['id']==identity:
            start,end=token.map
            return sum(map(len,lines[:start])),sum(map(len,lines[:end])),json.loads(lines[start+1].strip())
    raise HTTPException(404,'原文章中找不到该卡片，请重新读取')


def operate(db,source_id,data,actor):
    write_lock(db)
    signature=hashlib.sha256(json.dumps({'source':str(source_id),**data.model_dump(mode='json')},sort_keys=True).encode()).hexdigest()
    prior=db.scalar(select(RecordRevision.snapshot).where(RecordRevision.record_id==str(source_id),RecordRevision.actor_id==actor,RecordRevision.snapshot['entry_operation']['request_id'].as_string()==str(data.request_id)).limit(1))
    if prior:
        receipt=prior['entry_operation']
        if receipt['signature']!=signature:raise HTTPException(409,'请求标识已用于另一操作')
        return {**receipt,'replayed':True}
    source=get_record(db,source_id);target=get_record(db,data.target_id)
    if not get_type(db,target.type_id,lock=True).active:raise HTTPException(409,'目标文章类型已停用，不能接收卡片')
    entries(source.body)
    if source.body_format!=2 or target.body_format!=2:raise HTTPException(409,'请先明确保存为结构化正文格式，再操作卡片')
    if source.revision!=data.source_revision or target.revision!=data.target_revision:raise HTTPException(409,'文章已修改，请保存并重新读取后操作')
    if source.id==target.id and data.operation=='move':raise HTTPException(422,'跨文章移动必须选择另一篇文章')
    start,end,original=locate(source.body,str(data.entry_id))
    value=json.loads(json.dumps(original))
    if data.operation=='copy':value['id']=str(uuid.uuid4())
    existing={e['id'] for e in entries(target.body)}
    if value['id'] in existing:raise HTTPException(409,'目标文章已包含相同卡片身份')
    block=serialize(value)+'\n'
    if source.id==target.id:
        prefix=source.body[:end]
        bodies={source.id:prefix+('' if prefix.endswith('\n') else '\n')+block+source.body[end:]}
    else:
        bodies={target.id:target.body+('' if not target.body or target.body.endswith('\n\n') else '\n\n')+block}
        if data.operation=='move':bodies[source.id]=source.body[:start]+source.body[end:]
        else:bodies[source.id]=source.body  # durable idempotency receipt in a new source revision
    records={source.id:source,target.id:target}
    for identity,body in bodies.items():
        r=records[identity]
        if len(body)>300000:raise HTTPException(422,'目标正文超过长度限制')
        entries(body,published=r.status=='published')
    receipt={'request_id':str(data.request_id),'signature':signature,'operation':data.operation,
        'source_id':source.id,'target_id':target.id,'entry_id':value['id'],
        'source_revision':source.revision+1,'target_revision':target.revision+1}
    for identity,body in bodies.items():
        r=records[identity]
        result=db.execute(update(ContentRecord).where(ContentRecord.id==r.id,ContentRecord.revision==r.revision,ContentRecord.deleted_at.is_(None)).values(body=body,revision=r.revision+1,updated_at=now()))
        if result.rowcount!=1:raise HTTPException(409,'文章已发生并发修改')
    db.flush();db.expire_all()
    for identity in bodies:
        r=get_record(db,identity);revision_snapshot(db,r,actor)
        if identity==source.id:
            snapshot=db.get(RecordRevision,(r.id,r.revision))
            snapshot.snapshot={**snapshot.snapshot,'entry_operation':receipt}
    db.flush()
    return {**receipt,'replayed':False}
