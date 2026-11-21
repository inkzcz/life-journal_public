from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..dependencies import db_dep, require_dynamic_blog
from ..template_models import ContentTemplate
from ..template_schemas import TemplateIn, TemplateUpdate, TemplateCopy
from ..models import User
from ..services.archive import write_lock
from ..services.templates import get_template, template_data, save_template
from .content import commit

router=APIRouter(prefix='/api/admin/templates',dependencies=[Depends(require_dynamic_blog)])

@router.get('')
def listing(db:Session=Depends(db_dep)):
    return [{'id':t.id,'name':t.name,'slug':t.slug,'active':t.active,'revision':t.revision,'type_id':t.type_id} for t in db.scalars(select(ContentTemplate).order_by(ContentTemplate.name,ContentTemplate.id))]

@router.post('')
def create(data:TemplateIn,db:Session=Depends(db_dep),user:User=Depends(require_dynamic_blog)):
    write_lock(db);t=save_template(db,data,user.id);commit(db);return template_data(db,t)

@router.get('/presets')
def initial_presets():
    from ..template_presets import presets
    return presets()

@router.get('/{id}/defaults')
def defaults(id:UUID,db:Session=Depends(db_dep)):
    t=get_template(db,id);initial=template_data(db,t,1);latest=template_data(db,t)
    known={f['key'] for f in initial['fields']}
    extra=[f for f in latest['fields'] if f['key'] not in known]
    for f in extra:f['field'].update(active=False,required=False)
    initial['fields']+=extra
    # Choice option identities added later must also remain present.
    current={f['key']:f for f in latest['fields']}
    for f in initial['fields']:
        if f['field']['kind'] in {'select','multiselect'}:
            options=f['field']['rules'].get('options',[]);ids={o['id'] for o in options}
            options.extend({**o,'active':False} for o in current[f['key']]['field']['rules'].get('options',[]) if o['id'] not in ids)
    initial.update(revision=t.revision,expected_type_revision=latest['expected_type_revision'],name=t.name,slug=t.slug,active=t.active)
    return initial

@router.get('/{id}')
def read(id:UUID,db:Session=Depends(db_dep)):
    return template_data(db,get_template(db,id))

@router.put('/{id}')
def edit(id:UUID,data:TemplateUpdate,db:Session=Depends(db_dep),user:User=Depends(require_dynamic_blog)):
    write_lock(db);t=save_template(db,data,user.id,get_template(db,id));commit(db);return template_data(db,t)

@router.post('/{id}/copy')
def copy(id:UUID,data:TemplateCopy,db:Session=Depends(db_dep),user:User=Depends(require_dynamic_blog)):
    write_lock(db);t=get_template(db,id)
    if data.expected_revision!=t.revision:raise HTTPException(409,'模板已更新，请重新读取后复制')
    source=template_data(db,t)
    for f in source['fields']:f['field']['id']=None
    payload=TemplateIn(slug=data.slug,name=data.name,description=t.description,fields=source['fields'],modules=source['modules'])
    result=save_template(db,payload,user.id)
    from ..v5_models import FoodContentType
    if db.get(FoodContentType,t.type_id):db.add(FoodContentType(type_id=result.type_id,template_id=result.id))
    commit(db);return template_data(db,result)
