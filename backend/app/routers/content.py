"""Admin-only, feature-gated dynamic content. No public/private reader API is added."""
import uuid
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer
from ..dependencies import db_dep, require_dynamic_blog
from ..models import User, now
from ..services.archive import write_lock, replace_connections
from ..content_models import ContentType, ContentRecord
from ..content_schemas import TypeCreate, TypeUpdate, RecordCreate, RecordUpdate, DeleteIn
from ..services.content import (get_type, type_data, fields_for, save_version, record_values,
                               get_record, record_data, revision_snapshot, apply_record_update, record_summaries)

router=APIRouter(prefix='/api/admin/content',dependencies=[Depends(require_dynamic_blog)])


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'标识已存在或关联约束冲突，请重新读取后重试') from None


@router.get('/types')
def list_types(db:Session=Depends(db_dep)):
    return [{'id':t.id,'name':t.name,'slug':t.slug,'description':t.description,'active':t.active,'revision':t.revision}
            for t in db.scalars(select(ContentType).order_by(ContentType.created_at.desc(),ContentType.id))]


@router.post('/types')
def create_type(data:TypeCreate,db:Session=Depends(db_dep),user:User=Depends(require_dynamic_blog)):
    if db.scalar(select(ContentType.id).where(ContentType.slug==data.slug)) is not None:
        raise HTTPException(409,'稳定标识已存在')
    t=ContentType(id=str(uuid.uuid4()),slug=data.slug,name=data.name,description=data.description,active=data.active,revision=1)
    db.add(t)
    try:
        db.flush();save_version(db,t,data,user.id);commit(db)
    except IntegrityError:
        db.rollback();raise HTTPException(409,'稳定标识冲突，请重新读取') from None
    return type_data(db,t)


@router.post('/types/default-article')
def resolve_default_article(db:Session=Depends(db_dep),user:User=Depends(require_dynamic_blog)):
    from ..services.content import default_article_type
    try:
        result=default_article_type(db,user.id)
        commit(db)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'基础文章类型正在初始化，请重新尝试') from None
    return type_data(db,result)


@router.get('/types/{id}')
def read_type(id:UUID,db:Session=Depends(db_dep)):
    return type_data(db,get_type(db,id))


@router.get('/types/{id}/versions/{number}')
def read_type_version(id:UUID,number:int,db:Session=Depends(db_dep)):
    return type_data(db,get_type(db,id),version=number)


@router.put('/types/{id}')
def update_type(id:UUID,data:TypeUpdate,db:Session=Depends(db_dep),user:User=Depends(require_dynamic_blog)):
    t=get_type(db,id,lock=True)
    if t.slug!=data.slug:raise HTTPException(422,'稳定标识创建后不可修改，可修改显示名称')
    if t.revision!=data.expected_revision:raise HTTPException(409,'类型配置已更新，请重新读取，避免覆盖其他页面')
    previous=fields_for(db,t.id,t.revision)
    result=db.execute(update(ContentType).where(ContentType.id==t.id,ContentType.revision==data.expected_revision)
                      .values(name=data.name,description=data.description,active=data.active,revision=data.expected_revision+1))
    if result.rowcount!=1:raise HTTPException(409,'类型配置已更新，请重新读取')
    db.refresh(t)
    save_version(db,t,data,user.id,previous=previous);commit(db)
    return type_data(db,t)


@router.get('/records')
def list_records(page:int=Query(1,ge=1,le=1000000),page_size:int=Query(20,ge=1,le=100),
                 type_state:str|None=Query(None,pattern='^(active|inactive)$'),sort:str=Query('date',pattern='^(date|updated)$'),status:str|None=Query(None,pattern='^(draft|published)$'),type_id:UUID | None=None,q:str=Query('',max_length=200),db:Session=Depends(db_dep)):
    query=select(ContentRecord).where(ContentRecord.deleted_at.is_(None))
    if status:query=query.where(ContentRecord.status==status)
    if type_state:query=query.where(ContentRecord.type_id.in_(select(ContentType.id).where(ContentType.active.is_(type_state=='active'))))
    if q:query=query.where(ContentRecord.title.icontains(q,autoescape=True))
    if type_id:query=query.where(ContentRecord.type_id==str(type_id))
    total=db.scalar(query.with_only_columns(func.count(),maintain_column_froms=True))
    items=record_summaries(db,query.order_by(ContentRecord.updated_at.desc() if sort=='updated' else ContentRecord.display_date.desc(),ContentRecord.id).offset((page-1)*page_size).limit(page_size))
    return {'items':items,'total':total,'page':page,'page_size':page_size}



@router.post('/records')
def create_record(data:RecordCreate,db:Session=Depends(db_dep),user:User=Depends(require_dynamic_blog)):
    from ..services.content import create_record_in_transaction
    r=create_record_in_transaction(db,data,user.id)
    commit(db)
    from ..services.itinerary_generation import after_publish
    r=after_publish(db,r,user.id,'draft')
    return record_data(db,r)


@router.get('/records/{id}')
def read_record(id:UUID,db:Session=Depends(db_dep)):
    return record_data(db,get_record(db,id))


@router.put('/records/{id}')
def update_record(id:UUID,data:RecordUpdate,db:Session=Depends(db_dep),user:User=Depends(require_dynamic_blog)):
    old=get_record(db,id);previous=old.status
    r=apply_record_update(db,old,data,user.id);commit(db)
    from ..services.itinerary_generation import after_publish
    r=after_publish(db,r,user.id,previous)
    return record_data(db,r)


@router.delete('/records/{id}')
def delete_record(id:UUID,data:DeleteIn,db:Session=Depends(db_dep),user:User=Depends(require_dynamic_blog)):
    write_lock(db)
    r=get_record(db,id)
    result=db.execute(update(ContentRecord).where(ContentRecord.id==r.id,ContentRecord.revision==data.expected_revision,
                                                 ContentRecord.deleted_at.is_(None))
                      .values(deleted_at=now(),updated_at=now(),revision=data.expected_revision+1))
    if result.rowcount!=1:raise HTTPException(409,'记录已被修改，请重新读取后删除')
    db.flush();db.expire_all();r=db.get(ContentRecord,r.id);revision_snapshot(db,r,user.id);commit(db)
    return {'ok':True}
