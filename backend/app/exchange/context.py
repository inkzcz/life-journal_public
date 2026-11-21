"""One source for offline specifications and online generation context; reads only."""
import hashlib,io,json,zipfile
from sqlalchemy import select
from fastapi import HTTPException
from ..content_models import ContentType
from ..template_models import ContentTemplate,TemplateVersion
from ..services.content import type_data
from .schemas import Exchange
from .syntax import registry
from .rules import merged



def dynamic_schema(definition,template):
    schema=Exchange.model_json_schema();record=schema['$defs']['Record'];props={}
    for f in definition['fields']:
        if not f['active']:continue
        kind=f['kind'];rules=f['rules']
        if kind in ('short_text','long_text','markdown'):
            cap={'food_shop':200,'food_city':100,'food_address':1000}.get(f.get('purpose'),1000 if kind=='short_text' else 300000)
            typed={'type':'string','maxLength':min(rules['max_length'] if rules.get('max_length') is not None else cap,cap)}
            if rules.get('min_length') is not None:typed['minLength']=rules['min_length']
        elif kind=='integer':
            typed={'type':'integer','minimum':max(float(rules['min_value']) if rules.get('min_value') is not None else -9007199254740991,-9007199254740991),'maximum':min(float(rules['max_value']) if rules.get('max_value') is not None else 9007199254740991,9007199254740991)}
        elif kind=='decimal':typed={'type':'string','maxLength':40,'pattern':r'^-?\d+(\.\d{1,6})?$','description':'十进制文本；数值上下界仍由服务端规则最终校验。'}
        elif kind=='date':typed={'type':'string','format':'date','pattern':r'^\d{4}-\d{2}-\d{2}$'}
        else:
            options=[str(o['id']) for o in rules.get('options',[]) if o['active']]
            typed={'type':'string','enum':options} if kind=='select' else {'type':'array','items':{'type':'string','enum':options},'uniqueItems':True,'maxItems':rules.get('max_items') or len(options)}
        props[f['id']]={'anyOf':[typed,{'type':'null'}],'title':f['name'],'description':f['description'],'x-required-on-publish':f['required'],'x-has-local-default':f.get('has_default',False),'x-server-rules':rules}
    record['properties']['values']={'type':'object','properties':props,'additionalProperties':False,'description':'键为当前真实稳定字段UUID；草稿允许必填值待补充，发布仍执行原校验。'}
    record['properties']['type_slug']['const']=definition['slug']
    record['properties']['schema_version']['const']=definition['version']
    if template:
        record['properties']['template_slug']['const']=template['slug'];record['properties']['template_version']['const']=template['version']
    return schema

def context(db,type_slug,template_slug=None,layers=()):
    ct=db.scalar(select(ContentType).where(ContentType.slug==type_slug,ContentType.active.is_(True)))
    if ct is None:raise HTTPException(422,'请映射到已有且启用的内容类型')
    t=db.scalar(select(ContentTemplate).where(ContentTemplate.type_id==ct.id))
    if template_slug is not None and (t is None or t.slug!=template_slug):raise HTTPException(422,'模板与内容类型不匹配')
    binding=None
    if t:
        if not t.active:raise HTTPException(409,'模板已停用')
        v=db.get(TemplateVersion,(t.id,t.revision))
        if v is None or v.schema_version!=ct.revision:raise HTTPException(409,'模板与字段版本不同步，请先整理模板配置')
        binding={'id':t.id,'slug':t.slug,'version':t.revision,'schema_version':v.schema_version}
    definition=type_data(db,ct)
    definition['fields']=[{k:v for k,v in f.items() if k!='default_value'} for f in definition['fields']]
    from .settings import layers as configured_layers
    effective_layers=(*configured_layers(db,type_slug,t.slug if t else None),*layers)
    from ..version import __version__
    result={'application_version':__version__,'format':'life-journal.exchange','format_version':1,'application_version_source':'VERSION',
            'type':definition,'template':binding,'rules':merged(*effective_layers),'syntax':registry(),
            'exchange_schema':dynamic_schema(definition,binding),
            'dates':{'display_date':'文章展示日期，不等于旅行或用餐日期','travel.start_date':'实际出发日期','travel.end_date':'实际返回日期，可缺省','values.food_date':'对应purpose=food_date的动态字段实际用餐日期，可缺省'},
            'tags':'通过records[].tags创建或关联现有正式Tag；正文#文本不是正式标签。',
            'privacy':'此规范不包含文章正文、照片、API Key或服务器内部路径。',
            'status':'所有确认导入仅创建新草稿，不覆盖现有文章。'}
    # Include the full current schema and preferences in the freshness token.
    encoded=json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    result['context_digest']=hashlib.sha256(encoded.encode()).hexdigest()
    return result


def specification_zip(value):
    """Generated exclusively from the actual context, never a parallel rule document."""
    ct=value['type'];record={'key':'story','type_slug':ct['slug'],'schema_version':ct['version'],'title':'请填写真实标题','display_date':None,'body':'请根据本人提供的真实素材写作。','tags':[],'values':{}}
    if value['template']:record.update(template_slug=value['template']['slug'],template_version=value['template']['version'])
    example=Exchange.model_validate({'format':'life-journal.exchange','version':1,'records':[record]})
    # Missing optional date/fields intentionally remain unresolved, never fabricated.
    example=example.model_dump(mode='json',exclude_none=True)
    import yaml
    metadata={'format':'life-journal.exchange','version':1,'record':{k:v for k,v in example['records'][0].items() if k!='body'}}
    md='---\n'+yaml.safe_dump(metadata,allow_unicode=True,sort_keys=False)+'---\n'+record['body']
    instructions='''# Life Journal 写作规范包
这是当前实际内容类型、模板、字段和偏好的只读快照。
阅读context.json与content-exchange.schema.json。输出JSON或带Front Matter的Markdown。
不猜测UUID、不编造日期/店名/地址/照片，不输出HTML或可执行代码。
媒体先声明key/path，在正文独立一行使用{{media:key}}；现有媒体必须由用户明确选择。
餐厅优先填records[].foods与places，网站负责生成既有@f及图片归属，不能自由拼接私有语法。
ZIP包含manifest.json、documents指定的内容文件及media.path明确声明的真实照片，不根据文件名猜测关系。
缺失事实留空并提醒补充。用户必须在网站预览、映射并确认，默认只创建草稿。
本规范包不包含私人文章或照片，请由用户自行决定向ChatGPT提供哪些素材。
'''
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('README.md',instructions)
        z.writestr('context.json',json.dumps(value,ensure_ascii=False,indent=2))
        z.writestr('content-exchange.schema.json',json.dumps(value['exchange_schema'],ensure_ascii=False,indent=2))
        z.writestr('example.json',json.dumps(example,ensure_ascii=False,indent=2));z.writestr('example.md',md)
        package=io.BytesIO()
        with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as p:
            p.writestr('manifest.json',json.dumps({'format':'life-journal.package','version':1,'documents':['example.json']}))
            p.writestr('example.json',json.dumps(example,ensure_ascii=False))
        z.writestr('example-package.zip',package.getvalue())
        z.writestr('zip-manifest.json',json.dumps({'format':'life-journal.package','version':1,'documents':['article.json']},indent=2))
    return stream.getvalue()
