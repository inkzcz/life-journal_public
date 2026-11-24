import uuid
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import select,delete
from sqlalchemy.exc import IntegrityError
from ..dependencies import db_dep,require_dynamic_blog
from ..models import now,AdminUser
from ..blog_models import Section,SectionType,NavigationItem
from ..content_models import ContentType,ContentRecord
from ..content_schemas import DeleteIn
from ..blog_schemas import SectionIn,SectionEdit,AppearanceEdit,LayoutEdit,NavEdit
from ..services.archive import write_lock,asset
from ..services.content import get_record
from ..services.blog import reader,config_data,save_config,section_data,sections_data,readable,available,section_query,page_records,detail,navigation,home

router=APIRouter(prefix='/api/blog',dependencies=[Depends(reader)])
admin=APIRouter(prefix='/api/admin/blog',dependencies=[Depends(require_dynamic_blog)])

def commit(db):
    try:db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'标识重复或引用冲突，请重新读取') from None

def get_section(db,id):
    s=db.get(Section,str(id))
    if not s:raise HTTPException(404,'栏目不存在')
    return s

def validate_section(db,data):
    if data.cover_id:asset(db,data.cover_id)
    for id in data.type_ids:
        if not db.get(ContentType,str(id)):raise HTTPException(422,'内容类型不存在')

def bind_types(db,s,data):
    db.execute(delete(SectionType).where(SectionType.section_id==s.id))
    for id in data.type_ids:db.add(SectionType(section_id=s.id,type_id=str(id)))

# About content is ordinary versioned site metadata, not a new article model.
from ..about_schemas import About,AboutEdit
from ..blog_models import SiteConfig

def about_data(db):
    row=db.scalar(select(SiteConfig).where(SiteConfig.key=='about'))
    return {**About.model_validate(row.value if row else {}).model_dump(),'revision':row.revision if row else 0}

@router.get('/about')
def about(db=Depends(db_dep)):
    return about_data(db)

@admin.put('/about')
def edit_about(data:AboutEdit,db=Depends(db_dep)):
    write_lock(db);save_config(db,'about',data.model_dump(exclude={'expected_revision'}),data.expected_revision);commit(db)
    return about_data(db)

@router.get('/build-info')
def build_metadata(user=Depends(reader),db=Depends(db_dep)):
    from ..build_info import build_info
    return build_info(admin=db.get(AdminUser,user.id) is not None)

@admin.get('/sections')
def manage_sections(db=Depends(db_dep)):
    return sections_data(db,db.scalars(select(Section).order_by(Section.position,Section.id)))

@admin.post('/sections')
def create_section(data:SectionIn,db=Depends(db_dep)):
    write_lock(db);validate_section(db,data)
    s=Section(id=str(uuid.uuid4()),**data.model_dump(exclude={'type_ids','cover_id'}),cover_id=str(data.cover_id) if data.cover_id else None)
    db.add(s)
    try:db.flush();bind_types(db,s,data);commit(db)
    except IntegrityError:db.rollback();raise HTTPException(409,'栏目标识已存在') from None
    return section_data(db,s)

@admin.put('/sections/{id}')
def edit_section(id:UUID,data:SectionEdit,db=Depends(db_dep)):
    write_lock(db);s=get_section(db,id)
    if s.revision!=data.expected_revision:raise HTTPException(409,'栏目已更新，请重新读取')
    if s.slug!=data.slug:raise HTTPException(422,'稳定链接标识创建后不可修改，可修改名称')
    validate_section(db,data)
    for k,v in data.model_dump(exclude={'type_ids','cover_id','expected_revision'}).items():setattr(s,k,v)
    s.cover_id=str(data.cover_id) if data.cover_id else None;s.revision+=1;s.updated_at=now();bind_types(db,s,data);commit(db)
    return section_data(db,s)

@admin.delete('/sections/{id}')
def disable_section(id:UUID,data:DeleteIn,db=Depends(db_dep)):
    write_lock(db);s=get_section(db,id)
    if s.revision!=data.expected_revision:raise HTTPException(409,'栏目已更新，请重新读取')
    s.active=False;s.revision+=1;s.updated_at=now();commit(db);return section_data(db,s)

@admin.get('/appearance')
def appearance(db=Depends(db_dep)):return config_data(db,'appearance')
@admin.put('/appearance')
def update_appearance(data:AppearanceEdit,db=Depends(db_dep)):
    write_lock(db)
    current=config_data(db,'appearance')
    value={'theme':data.theme if 'theme' in data.model_fields_set else current.get('theme',data.theme),
           'mode':data.mode if 'mode' in data.model_fields_set else current.get('mode',data.mode)}
    # Explicit legacy switches retain their historical color/default behavior.
    legacy_switch='theme' in data.model_fields_set and data.theme!=current.get('theme')
    for key in ['style','palette','combination_colors']:
        if key in data.model_fields_set:
            val=getattr(data,key)
            if val is not None:value[key]=val
        elif key in current and (key=='combination_colors' or not legacy_switch):
            value[key]=current[key]
    if 'colors' in data.model_fields_set:
        colors={theme:{mode:palette for mode,palette in modes.items() if palette}
                for theme,modes in data.colors.items() if any(modes.values())}
        if colors:value['colors']=colors
    elif 'colors' in current:value['colors']=current['colors']
    # Empty combination leaves are intentional reset tombstones: they suppress
    # legacy fallbacks without deleting a user's archived colors.
    save_config(db,'appearance',value,data.expected_revision);commit(db)
    return config_data(db,'appearance')
@admin.get('/layout')
def layout(db=Depends(db_dep)):return config_data(db,'layout')
@admin.put('/layout')
def update_layout(data:LayoutEdit,db=Depends(db_dep)):
    write_lock(db)
    for m in data.modules:
        if m.section_id:get_section(db,m.section_id)
        if m.type_id and not db.get(ContentType,str(m.type_id)):raise HTTPException(422,'内容类型不存在')
        for id in m.record_ids:get_record(db,id)
    save_config(db,'layout',data.model_dump(mode='json',exclude={'expected_revision'}),data.expected_revision);commit(db);return config_data(db,'layout')
@admin.get('/navigation')
def nav_config(db=Depends(db_dep)):
    return {'revision':config_data(db,'navigation')['revision'],'items':navigation(db,private=False)}
@admin.put('/navigation')
def update_navigation(data:NavEdit,db=Depends(db_dep)):
    write_lock(db)
    for n in data.items:
        if n.section_id:get_section(db,n.section_id)
        if n.record_id:get_record(db,n.record_id)
    save_config(db,'navigation',{},data.expected_revision)
    # Children first; full-tree replacement is a single revision-protected transaction.
    db.execute(delete(NavigationItem).where(NavigationItem.parent_id.is_not(None)));db.execute(delete(NavigationItem));db.flush()
    def add(n,i):db.add(NavigationItem(**n.model_dump(mode='json'),position=i))
    for i,n in enumerate(data.items):
        if n.parent_id is None:add(n,i)
    db.flush()
    for i,n in enumerate(data.items):
        if n.parent_id is not None:add(n,i)
    commit(db);return nav_config(db)
@admin.get('/preview/{id}')
def draft_preview(id:UUID,expected_revision:int|None=Query(None,ge=1),db=Depends(db_dep)):
    # Same short transaction lock as record/relationship writes; no revision is created.
    write_lock(db);r=get_record(db,id)
    if expected_revision is not None and r.revision!=expected_revision:
        raise HTTPException(409,'预览修订已变化，请返回编辑器核对并重新保存后预览')
    return {**detail(db,r),'preview_revision':r.revision}

@router.get('/site')
def site(db=Depends(db_dep),user=Depends(reader)):
    config=config_data(db,'layout')
    from ..site_text import reading_text_data
    return {'text':reading_text_data(db,config,db.get(AdminUser,user.id) is not None),'title':config['title'],'description':config['description'],'appearance':config_data(db,'appearance'),'navigation':navigation(db),'sections':sections_data(db,db.scalars(select(Section).where(Section.active.is_(True)).order_by(Section.position,Section.id)))}
@router.get('/home')
def homepage(db=Depends(db_dep)):return home(db)
@router.get('/sections/{slug}')
def section_page(slug:str,page:int=Query(1,ge=1,le=1000000),db=Depends(db_dep)):
    s=db.scalar(select(Section).where(Section.slug==slug,Section.active.is_(True)))
    if not s:raise HTTPException(404,'栏目不存在')
    return {'section':section_data(db,s),**page_records(db,section_query(readable(),s.id),page)}
@router.get('/records')
def records(page:int=Query(1,ge=1,le=1000000),db=Depends(db_dep)):
    return page_records(db,readable(),page)
@router.get('/records/{id}')
def record(id:UUID,db=Depends(db_dep)):
    r=available(db,id)
    if not r:raise HTTPException(404,'文章不存在')
    return detail(db,r)

@router.get('/timeline')
def life_timeline(record_mode:Literal['daily','travel']|None=None,year:int|None=Query(None,ge=1,le=9999),type_id:UUID|None=None,page:int=Query(1,ge=1,le=1000000),db=Depends(db_dep)):
    from ..services.life_feed import feed
    return feed(db,year,type_id,page,record_mode)

@router.get('/year-review/{year}')
def annual_review(year:int,record_mode:Literal['daily','travel']|None=None,type_id:UUID|None=None,page:int=Query(1,ge=1,le=1000000),db=Depends(db_dep)):
    if not 1<=year<=9999:raise HTTPException(422,'年份超出范围')
    from ..services.life_feed import review
    return review(db,year,type_id,page,record_mode)


@router.get('/records/{id}/neighbors')
def neighbors(id:UUID,db=Depends(db_dep)):
    from ..services.blog import adjacent_records
    r=available(db,id)
    if not r:raise HTTPException(404,'文章不存在')
    return adjacent_records(db,r)

# Global presentation metadata lives in the existing versioned SiteConfig JSON.
from ..blog_schemas import Typography,TypographyEdit
from ..blog_models import SiteConfig

def typography_data(db):
    row=db.scalar(select(SiteConfig).where(SiteConfig.key=='typography'))
    return {**Typography.model_validate(row.value if row else {}).model_dump(),'revision':row.revision if row else 0}

@router.get('/typography')
def typography(db=Depends(db_dep)):
    return typography_data(db)

@admin.put('/typography')
def update_typography(data:TypographyEdit,db=Depends(db_dep)):
    write_lock(db)
    save_config(db,'typography',data.model_dump(exclude={'expected_revision'}),data.expected_revision)
    commit(db)
    return typography_data(db)
