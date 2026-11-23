"""Versioned configuration and typed values. All writes remain in the caller's transaction."""
import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from fastapi import HTTPException
from sqlalchemy import select, update
from ..content_models import ContentType, ContentTypeVersion, FieldDefinition, VersionField, ContentRecord, RecordRevision
from ..models import now


def invalid(message):
    raise HTTPException(422,message)


def get_type(db,id,lock=False):
    query=select(ContentType).where(ContentType.id==str(id))
    if lock:
        query=query.with_for_update()
    result=db.scalar(query)
    if result is None:
        raise HTTPException(404,'内容类型不存在')
    return result


def fields_for(db,type_id,number):
    if db.get(ContentTypeVersion,(type_id,number)) is None:
        raise HTTPException(404,'字段版本不存在')
    rows=db.execute(select(VersionField,FieldDefinition.kind).join(FieldDefinition,VersionField.field_id==FieldDefinition.id)
                    .where(VersionField.type_id==type_id,VersionField.version==number).order_by(VersionField.position)).all()
    return [{'id':f.field_id,'kind':kind,'name':f.name,'description':f.description,'position':f.position,
             'searchable':f.rules.get('searchable',False),'required':f.required,'active':f.active,'has_default':f.has_default,
             'default_value':f.default_value,**({'purpose':f.rules['purpose']} if f.rules.get('purpose') else {}),'rules':{k:v for k,v in f.rules.items() if k not in ('searchable','purpose')}} for f,kind in rows]


def type_data(db,t,version=None):
    from ..v5_models import FoodContentType
    return {'id':t.id,'slug':t.slug,'name':t.name,'description':t.description,'active':t.active,
            'is_food':db.get(FoodContentType,t.id) is not None,'revision':t.revision,'version':version or t.revision,'fields':fields_for(db,t.id,version or t.revision)}


def default_article_type(db, actor_id):
    """Resolve a field-free base type without reconfiguring existing types.

    The existing transaction lock serializes lazy initialization on PG and SQLite.
    UUIDs are generated identities, never assumed database IDs. A conflicting or
    later-customized type remains intact; a fresh compatible base is used instead.
    The caller owns commit/rollback, as for every other content operation.
    """
    from .archive import write_lock
    from ..content_schemas import TypeCreate
    from ..template_models import ContentTemplate
    from ..v5_models import FoodContentType
    write_lock(db)
    prefix='life-journal-article'
    candidates=list(db.scalars(select(ContentType).where(
        (ContentType.slug==prefix) | ContentType.slug.startswith(prefix+'-')
    ).order_by(ContentType.created_at,ContentType.id)))
    for candidate in candidates:
        if (candidate.active and not fields_for(db,candidate.id,candidate.revision)
                and db.scalar(select(ContentTemplate.id).where(ContentTemplate.type_id==candidate.id)) is None
                and db.get(FoodContentType,candidate.id) is None):
            return candidate
    occupied={t.slug for t in candidates}
    slug=prefix
    while slug in occupied:
        slug=prefix+'-'+uuid.uuid4().hex
    data=TypeCreate(slug=slug,name='文章',description='日常记录与旅行记录共用的基础文章类型。')
    result=ContentType(id=str(uuid.uuid4()),slug=slug,name=data.name,
                       description=data.description,active=True,revision=1)
    db.add(result);db.flush();save_version(db,result,data,actor_id)
    return result


def clean_value(field,value,required=False):
    name=field['name'];kind=field['kind'];rules=field['rules']
    if value is None:
        if required:
            invalid(f'{name}：此字段必填')
        return None
    if kind in {'short_text','long_text','markdown'}:
        if not isinstance(value,str):invalid(f'{name}：需要文本')
        maximum={'food_shop':200,'food_city':100,'food_address':1000}.get(field.get('purpose'),1000 if kind=='short_text' else 300000)
        if len(value)>maximum:invalid(f'{name}：文本过长')
        if required and not value.strip():invalid(f'{name}：此字段必填')
        if rules.get('min_length') is not None and len(value)<rules['min_length']:invalid(f'{name}：文本过短')
        if rules.get('max_length') is not None and len(value)>rules['max_length']:invalid(f'{name}：文本过长')
    elif kind in {'integer','decimal'}:
        if kind=='integer':
            if type(value) is not int or abs(value)>9007199254740991:invalid(f'{name}：需要安全范围内的整数')
            number=Decimal(value)
        else:
            if not isinstance(value,str) or len(value)>40 or not re.fullmatch(r'-?\d+(\.\d{1,6})?',value):invalid(f'{name}：小数需以十进制文本提交，最多6位小数')
            try:number=Decimal(value)
            except InvalidOperation:invalid(f'{name}：无效小数')
            if not number.is_finite() or abs(number)>Decimal('9007199254740991'):invalid(f'{name}：小数超出范围')
            value=format(number,'f')
        for key,compare in [('min_value',lambda x,y:x<y),('max_value',lambda x,y:x>y)]:
            if rules.get(key) is not None and compare(number,Decimal(str(rules[key]))):invalid(f'{name}：数值超出允许范围')
    elif kind=='date':
        try:
            if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:raise ValueError()
        except ValueError:invalid(f'{name}：需要YYYY-MM-DD日期')
        if rules.get('min_date') and value<rules['min_date']:invalid(f'{name}：日期过早')
        if rules.get('max_date') and value>rules['max_date']:invalid(f'{name}：日期过晚')
    else:
        allowed={o['id'] for o in rules.get('options',[]) if o['active']}
        if kind=='select':
            if not isinstance(value,str) or value not in allowed:invalid(f'{name}：请选择有效选项')
        else:
            if not isinstance(value,list) or any(not isinstance(x,str) or x not in allowed for x in value):invalid(f'{name}：请选择有效选项')
            if len(value)!=len(set(value)) or len(value)>rules.get('max_items',50):invalid(f'{name}：选项重复或过多')
            if required and not value:invalid(f'{name}：此字段必填')
    return value


def save_version(db,t,data,user_id,previous=None):
    known={f.id:f for f in db.scalars(select(FieldDefinition).where(FieldDefinition.type_id==t.id))}
    submitted={str(f.id) for f in data.fields if f.id is not None}
    if not set(known)<=submitted:
        invalid('已有字段不能直接删除，请保留字段并停用')
    previous={f['id']:f for f in previous or []}
    db.add(ContentTypeVersion(type_id=t.id,number=t.revision,created_by=user_id));db.flush()
    purposes=set()
    for field in data.fields:
        fid=str(field.id) if field.id else str(uuid.uuid4())
        if field.id:
            identity=known.get(fid)
            if identity is None:invalid('字段标识不属于此内容类型')
            if identity.kind!=field.kind:invalid('已有字段的种类不能修改，请新建字段并停用旧字段')
        else:
            db.add(FieldDefinition(id=fid,type_id=t.id,kind=field.kind));db.flush()
        rules=field.rules.model_dump(mode='json',exclude_none=True)
        if field.searchable:rules['searchable']=True
        old_purpose=previous.get(fid,{}).get('purpose')
        if old_purpose and field.purpose and old_purpose!=field.purpose:invalid('已有字段语义不可修改，请新增字段')
        purpose=field.purpose or old_purpose
        if purpose and field.active:
            if purpose in purposes:invalid('美食字段语义不能重复')
            purposes.add(purpose)
        if purpose:rules['purpose']=purpose
        old=previous.get(fid)
        if old and field.kind in {'select','multiselect'}:
            old_ids={o['id'] for o in old['rules']['options']}
            if not old_ids<={o['id'] for o in rules['options']}:invalid('已有选项不能移除，请停用选项')
        spec={**field.model_dump(mode='json'),'id':fid,'purpose':purpose,'rules':rules}
        default=clean_value(spec,field.default_value,field.required) if field.has_default else None
        db.add(VersionField(type_id=t.id,version=t.revision,field_id=fid,name=field.name,
                            description=field.description,position=field.position,required=field.required,
                            active=field.active,has_default=field.has_default,default_value=default,rules=rules))


def record_values(fields,values,published,previous=None,creating=False):
    known={f['id']:f for f in fields};previous=previous or {}
    if set(values)-set(known):invalid('记录包含未知字段')
    result={}
    for fid,f in known.items():
        if not f['active']:
            if fid in values and (creating or fid not in previous or values[fid]!=previous[fid]):invalid(f"{f['name']}：已停用，不能写入新值")
            if fid in previous:result[fid]=previous[fid]
            continue
        if fid in values:
            value=values[fid]
        elif creating and f['has_default']:
            value=f['default_value']
        else:
            value=None
        result[fid]=clean_value(f,value,required=published and f['required'])
    return result


def record_data(db,r,summary=False,type_row=None,*,marker_protocol=True):
    t=type_row if type_row is not None else get_type(db,r.type_id)
    result={'id':r.id,'type_id':r.type_id,'type_name':t.name,'type_active':t.active,
            'schema_version':r.schema_version,'current_type_version':t.revision,'title':r.title,
            'display_date':r.display_date.isoformat(),'status':r.status,'revision':r.revision,
            'created_at':r.created_at.isoformat(),'updated_at':r.updated_at.isoformat(),
            'summary':r.summary,
            'deleted_at':r.deleted_at.isoformat() if r.deleted_at else None}
    if not summary:
        from ..v5_models import FoodContentType
        result['is_food']=db.get(FoodContentType,r.type_id) is not None
        from .archive import connections_data
        from .templates import binding_data
        from .life import life_data
        from .tags import record_tags
        from .organization import article_folder
        from ..v5_models import RecordMediaFolder
        folder=db.get(RecordMediaFolder,r.id)
        result['media_folder_id']=folder.folder_id if folder else None
        from ..content_models import RecordBodyMedia
        result['body_media_ids']=list(db.scalars(select(RecordBodyMedia.media_id).where(RecordBodyMedia.record_id==r.id).order_by(RecordBodyMedia.media_id)))
        result['tags']=record_tags(db,[r.id]).get(r.id,[])
        result['tag_ids']=[t['id'] for t in result['tags']]
        result['life']=life_data(db,r.id)
        from .experiences import options
        result['article']=options(db,r)
        if marker_protocol:
            from .experiences import syntax_version
            result['marker_version']=syntax_version(db,r)
        from .itinerary_generation import state
        result['itinerary_generation']=state(db,r)
        from ..archive_models import RecordMarkedPlace
        result['marked_places']=[{'source_key':p.source_key,'place_id':p.place_id} for p in db.scalars(select(RecordMarkedPlace).where(RecordMarkedPlace.record_id==r.id).order_by(RecordMarkedPlace.source_key))]
        result['template']=binding_data(db,r)
        result.update(summary=r.summary,body=r.body,body_format=r.body_format,values=r.values,fields=fields_for(db,r.type_id,r.schema_version),connections=connections_data(db,r.id))
    return result


def revision_snapshot(db,r,actor,*,marker_version=None):
    from .body_media import sync_body, snapshot_refs
    from .experiences import sync as sync_experiences
    sync_experiences(db,r)
    sync_body(db,r)
    from .organization import article_folder
    if r.deleted_at is None:article_folder(db,r)
    from .food import sync as sync_food
    sync_food(db,r)
    snapshot=record_data(db,r)
    if marker_version is not None:snapshot['marker_version']=marker_version
    from ..life_models import TripActivity
    from ..archive_models import RecordPlace
    snapshot['markdown_place_ids']=list(db.scalars(select(RecordPlace.place_id).where(RecordPlace.record_id==r.id,RecordPlace.markdown_owned.is_(True)).order_by(RecordPlace.place_id)))
    snapshot['markdown_activity_ids']=list(db.scalars(select(TripActivity.id).where(TripActivity.record_id==r.id,TripActivity.markdown_owned.is_(True),TripActivity.active.is_(True)).order_by(TripActivity.id)))
    db.add(RecordRevision(record_id=r.id,number=r.revision,snapshot=snapshot,actor_id=actor))
    db.flush()
    snapshot_refs(db,r.id,r.revision,snapshot)
    from .places import snapshot_refs as place_refs
    place_refs(db,r.id,r.revision,snapshot)


def get_record(db,id):
    r=db.get(ContentRecord,str(id))
    if r is None or r.deleted_at is not None:raise HTTPException(404,'记录不存在')
    return r


def apply_record_update(db,r,data,actor,*,before_snapshot=None):
    from .archive import write_lock, replace_connections
    write_lock(db)
    from .experiences import normalize_quick,syntax_version
    submitted_body=data.body
    data.body=normalize_quick(data.body,r.body,modern=syntax_version(db,r)==2)
    if data.body!=submitted_body:
        from .body_media import blocks
        from .experiences import entries
        initial_format=data.body_format if data.body_format is not None else r.body_format
        if initial_format!=2 and (blocks(submitted_body,2) or entries(submitted_body)):raise HTTPException(422,'原文含旧格式字面资源块，请先明确转换正文格式，未自动激活资源')
        data.body_format=2
    t=get_type(db,r.type_id,lock=True)
    if data.schema_version not in {r.schema_version,t.revision}:invalid('只能使用原字段版本或最新版本')
    if r.revision!=data.expected_revision:raise HTTPException(409,'记录已被其他页面修改，请重新读取；当前草稿不会自动覆盖服务器')
    fields=fields_for(db,t.id,data.schema_version)
    values=record_values(fields,data.values,data.status=='published',previous=r.values)
    result=db.execute(update(ContentRecord).where(ContentRecord.id==r.id,ContentRecord.revision==data.expected_revision,
                                                 ContentRecord.deleted_at.is_(None))
                      .values(title=data.title,body=data.body,summary=r.summary if data.summary is None else data.summary,body_format=data.body_format if data.body_format is not None else r.body_format,display_date=data.display_date,status=data.status,
                              values=values,schema_version=data.schema_version,revision=data.expected_revision+1,updated_at=now()))
    if result.rowcount!=1:raise HTTPException(409,'记录已修改，请重新读取')
    db.flush();db.expire_all();r=get_record(db,r.id)
    from .templates import bind_record
    bind_record(db,r,data.template)
    replace_connections(db,r,data.connections)
    from .life import save_life
    from .tags import replace_tags
    replace_tags(db,r,data.tag_ids)
    from .marked_places import sync
    sync(db,r)
    from .experiences import sync as sync_experiences
    sync_experiences(db,r)
    save_life(db,r,data.life)
    from .experiences import save_options
    save_options(db,r,data.article)
    from .marked_places import prune_connections
    prune_connections(db,r)
    from .organization import adopt_uploads
    adopt_uploads(db,r,data.new_media_ids,actor)
    if before_snapshot is not None:before_snapshot(r)
    revision_snapshot(db,r,actor)
    return r


def record_summaries(db,query):
    from sqlalchemy.orm import defer,undefer
    rows=db.execute(query.add_columns(ContentType).join(ContentType,ContentRecord.type_id==ContentType.id)
        .options(defer(ContentRecord.body),defer(ContentRecord.values),undefer(ContentRecord.summary))).all()
    return [record_data(db,r,summary=True,type_row=t) for r,t in rows]


def create_record_in_transaction(db,data,actor_id,*,snapshot=True,record_id=None):
    """Reuse normal creation without committing: caller owns atomic multi-create.

    Authorization belongs to the authenticated entry point. Existing model, field,
    template, resource and revision checks remain mandatory here.
    """
    from .archive import write_lock, replace_connections
    write_lock(db)
    from .experiences import normalize_quick
    submitted_body=data.body
    data.body=normalize_quick(data.body,modern=data.marker_version==2)
    if data.body!=submitted_body:
        from .body_media import blocks
        from .experiences import entries
        if data.body_format!=2 and (blocks(submitted_body,2) or entries(submitted_body)):raise HTTPException(422,'原文含旧格式字面资源块，请先明确转换正文格式，未自动激活资源')
        data.body_format=2
    t=get_type(db,data.type_id,lock=True)
    if not t.active:raise HTTPException(409,'内容类型已停用，不能新建记录')
    if data.schema_version!=t.revision:raise HTTPException(409,'字段配置已更新，请重新加载类型配置后新建')
    fields=fields_for(db,t.id,t.revision)
    values=record_values(fields,data.values,data.status=='published',creating=True)
    rid=str(uuid.UUID(str(record_id))) if record_id is not None else str(uuid.uuid4())
    if db.get(ContentRecord,rid) is not None:raise HTTPException(409,'新记录身份已经存在，不能覆盖原记录')
    r=ContentRecord(id=rid,type_id=t.id,schema_version=t.revision,title=data.title,
                    body=data.body,summary=data.summary or '',body_format=data.body_format or 1,display_date=data.display_date,status=data.status,values=values,revision=1)
    from ..services.templates import bind_record
    db.add(r);db.flush();bind_record(db,r,data.template,creating=True);replace_connections(db,r,data.connections)
    from ..services.life import save_life
    from ..services.tags import replace_tags
    replace_tags(db,r,data.tag_ids)
    from ..services.marked_places import sync
    sync(db,r)
    from .experiences import sync as sync_experiences
    sync_experiences(db,r)
    save_life(db,r,data.life)
    from .experiences import save_options
    save_options(db,r,data.article)
    from ..services.marked_places import prune_connections
    prune_connections(db,r)
    from ..services.organization import adopt_uploads
    adopt_uploads(db,r,data.new_media_ids,actor_id)
    if snapshot:revision_snapshot(db,r,actor_id,marker_version=data.marker_version)
    return r
