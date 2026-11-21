"""Display-only allowlist: actions, errors and security warnings are excluded."""
from fastapi import APIRouter,Depends
from pydantic import Field,field_validator
from sqlalchemy import select
from .archive_schemas import StrictModel
from .dependencies import db_dep,current_user,require_admin
from .services.blog import save_config,config_data
from .services.archive import write_lock
from .blog_models import SiteConfig
DEFAULTS={'site.subtitle':'收藏日常，留住时光。','home.welcome':'生活值得慢慢收藏','home.introduction':'在这里，安放故事与值得记住的片刻。','nav.home':'首页','nav.timeline':'生活时间线','nav.archive':'生活归档','nav.year':'年度回顾','nav.sections':'所有栏目','admin.blog':'私人 Blog','page.stories':'所有故事','admin.content':'内容管理','admin.templates':'内容模板','admin.tags':'标签管理','admin.trash':'回收站','admin.maintenance':'备份与恢复','admin.site':'网站设置','admin.system':'系统状态','admin.help':'使用帮助','page.timeline':'生活时间线','page.archive':'生活归档','page.year':'年度回顾','page.sections':'所有栏目','footer.description':'故事与时光，只留给你信任的人。','footer.copyright':'Life Journal · 私人生活档案'}
class TextEdit(StrictModel):
    expected_revision:int=Field(ge=0)
    title:str|None=Field(default=None,min_length=1,max_length=100)
    expected_layout_revision:int|None=Field(default=None,ge=0)
    values:dict[str,str]=Field(default_factory=dict,max_length=len(DEFAULTS))
    @field_validator('values')
    @classmethod
    def valid(cls,v):
        for key,value in v.items():
            if key not in DEFAULTS:raise ValueError('不支持自定义此系统文字')
            if not value.strip() or len(value)>(2000 if key in {'home.introduction','footer.description'} else 200):raise ValueError('文字为空或超过长度限制')
            if any(ord(c)<32 and c not in '\n\t' for c in value):raise ValueError('文字包含控制字符')
        return v

def text_data(db,layout=None):
    row=db.scalar(select(SiteConfig).where(SiteConfig.key=='site_text'))
    layout=layout or config_data(db,'layout')
    return {'site_name':layout['title'],'layout_revision':layout['revision'],'values':row.value if row else {},'defaults':DEFAULTS,'revision':row.revision if row else 0}
router=APIRouter()
@router.get('/api/site/text',dependencies=[Depends(require_admin)])
def read(db=Depends(db_dep)):return text_data(db)
@router.put('/api/admin/site/text',dependencies=[Depends(require_admin)])
def save(data:TextEdit,db=Depends(db_dep)):
    write_lock(db)
    if data.title is not None:
        from fastapi import HTTPException
        if not data.title.strip() or data.expected_layout_revision is None:raise HTTPException(422,'网站名称不能为空，且需提供已读取的配置修订号')
        layout=config_data(db,'layout')
        save_config(db,'layout',{**{k:v for k,v in layout.items() if k!='revision'},'title':data.title.strip()},data.expected_layout_revision)
    save_config(db,'site_text',data.values,data.expected_revision)
    db.commit();return text_data(db)


def reading_text_data(db,layout,is_admin=False):
    full=text_data(db,layout)
    allowed={key for key in DEFAULTS if is_admin or not key.startswith('admin.')}
    # Reading DTO never exposes configuration revision metadata. Admin-only
    # display names are also absent for ordinary readers.
    return {'site_name':full['site_name'],
            'values':{k:v for k,v in full['values'].items() if k in allowed},
            'defaults':{k:v for k,v in full['defaults'].items() if k in allowed}}
