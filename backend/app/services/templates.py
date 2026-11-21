"""Templates compose existing fields. All mutations use the archive transaction lock."""
import uuid
from fastapi import HTTPException
from sqlalchemy import select
from ..template_models import ContentTemplate, TemplateVersion, RecordTemplate
from ..template_schemas import TemplateIn
from ..content_schemas import TypeCreate
from ..content_models import ContentType
from .content import get_type, fields_for, save_version, invalid


def get_template(db,id):
    t=db.get(ContentTemplate,str(id))
    if t is None: raise HTTPException(404,'模板不存在')
    return t


def template_data(db,t,number=None):
    v=db.get(TemplateVersion,(t.id,number or t.revision))
    if v is None: raise HTTPException(404,'模板版本不存在')
    groups={f['id']:f['group'] for f in v.config['form']}
    return {'id':t.id,'slug':t.slug,'name':t.name,'description':t.description,'active':t.active,
            'revision':t.revision,'version':v.number,'type_id':v.type_id,'schema_version':v.schema_version,
            'expected_type_revision':get_type(db,v.type_id).revision,
            'fields':[{'key':f['id'],'group':groups.get(f['id'],'基本信息'),'field':f} for f in fields_for(db,v.type_id,get_type(db,v.type_id).revision if number is None else v.schema_version)],
            'modules':v.config['modules']}


def save_template(db,data,actor,t=None):
    duplicate=db.scalar(select(ContentTemplate.id).where(ContentTemplate.slug==data.slug))
    if duplicate and (t is None or duplicate!=t.id): raise HTTPException(409,'模板稳定标识已存在')
    if t:
        if t.slug!=data.slug: invalid('稳定标识不可修改')
        if t.revision!=data.expected_revision: raise HTTPException(409,'模板已更新，请重新读取，输入已保留')
        ct=get_type(db,t.type_id,lock=True)
        if ct.revision!=data.expected_type_revision: raise HTTPException(409,'动态字段已更新，请重新读取并检查配置')
        previous=fields_for(db,ct.id,ct.revision)
        submitted={str(f.field.id):f.field for f in data.fields if f.field.id}
        for f in previous:
            if f['active'] and f['required'] and f['id'] in submitted and not submitted[f['id']].active and submitted[f['id']].required:
                invalid('移除字段前请先取消必填；历史值将保留')
        ct.revision+=1;t.revision+=1
    else:
        previous=[]
        # One ordinary dynamic content type per template; no domain-specific tables.
        ct=ContentType(id=str(uuid.uuid4()),slug='tpl-'+str(uuid.uuid4()),name=data.name,description=data.description,active=True,revision=1)
        db.add(ct);db.flush()
        t=ContentTemplate(id=str(uuid.uuid4()),slug=data.slug,name=data.name,description=data.description,type_id=ct.id,active=data.active,revision=1)
        db.add(t);db.flush()
    spec=TypeCreate(slug=ct.slug,name=data.name,description=data.description,active=ct.active,
                    fields=[f.field.model_copy(update={'position':i}) for i,f in enumerate(data.fields)])
    save_version(db,ct,spec,actor,previous=previous)
    db.flush()
    actual=fields_for(db,ct.id,ct.revision)
    mapping={str(f.key):actual[i]['id'] for i,f in enumerate(data.fields)}
    modules=[{**m.model_dump(mode='json'),'field_ids':[mapping[str(id)] for id in m.field_ids]} for m in data.modules]
    config={'form':[{'id':mapping[str(f.key)],'group':f.group.strip() or '基本信息'} for f in data.fields],'modules':modules}
    t.name=data.name;t.description=data.description;t.active=data.active
    ct.name=data.name;ct.description=data.description
    db.add(TemplateVersion(template_id=t.id,number=t.revision,type_id=ct.id,schema_version=ct.revision,config=config,created_by=actor))
    db.flush()
    return t


def binding_data(db,r):
    b=db.get(RecordTemplate,r.id)
    if not b:return None
    v=db.get(TemplateVersion,(b.template_id,b.version));t=get_template(db,b.template_id)
    return {'id':b.template_id,'version':b.version,'name':t.name,'current_version':t.revision,'active':t.active,'config':v.config}


def bind_record(db,r,requested,creating=False):
    old=db.get(RecordTemplate,r.id)
    if requested is None:
        if old:
            v=db.get(TemplateVersion,(old.template_id,old.version))
            if (v.type_id,v.schema_version)!=(r.type_id,r.schema_version):
                raise HTTPException(409,'模板记录升级字段时必须同时选择对应的模板版本')
        elif creating and db.scalar(select(ContentTemplate.id).where(ContentTemplate.type_id==r.type_id)):
            raise HTTPException(409,'此类型属于模板，请从模板新建记录')
        return
    t=get_template(db,requested.id);v=db.get(TemplateVersion,(t.id,requested.version))
    if v is None or (v.type_id,v.schema_version)!=(r.type_id,r.schema_version): invalid('模板与内容字段版本不匹配')
    same=old and (old.template_id,old.version)==(t.id,v.number)
    if not same:
        if not t.active: raise HTTPException(409,'模板已停用，不能新建或切换到此模板')
        if requested.version!=t.revision: raise HTTPException(409,'模板已更新，请重新读取')
        if old and old.template_id!=t.id: invalid('不能切换至不同字段身份的模板，请复制内容新建')
    if old:old.template_id=t.id;old.version=v.number
    else:db.add(RecordTemplate(record_id=r.id,template_id=t.id,version=v.number))
    db.flush()
