"""Read-only normalization against real schemas. No content/media is created here."""
import re
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select
from ..archive_models import MediaAsset,Place
from ..content_models import ContentRecord
from ..services.content import record_values
from ..services.markdown_marks import parse as marks
from ..services.body_media import blocks
from ..services.experiences import entries
from ..services.resource_usage import markdown_media_ids
from ..services.tags import normalize
from .context import context
from .syntax import place_mark


def field_values(fields,values):
    """Prefer stable IDs; accept an unambiguous label/purpose only as explicit mapping."""
    mapped={};warnings=[]
    for key,value in values.items():
        found=[f for f in fields if f['id']==key]
        if not found:found=[f for f in fields if f['active'] and (f['name']==key or f.get('purpose')==key)]
        if len(found)!=1:raise HTTPException(422,'字段未匹配或名称不唯一，请映射到稳定字段ID：'+key[:100])
        fid=found[0]['id']
        if fid in mapped:raise HTTPException(422,'多个输入映射到同一字段')
        mapped[fid]=value
        if fid!=key:warnings.append({'source':key,'field_id':fid})
    return record_values(fields,mapped,False,creating=True),warnings



def placeholders(body):
    from ..services.body_media import narrative_parser
    lines=body.splitlines();out=[]
    for token in narrative_parser().parse(body):
        if token.type!='inline' or not token.map or token.map[1]-token.map[0]!=1:continue
        raw=lines[token.map[0]].strip()
        if raw!=token.content.strip():continue  # escaped literals stay literal
        match=re.fullmatch(r'\{\{(media|place):([A-Za-z][A-Za-z0-9_-]{0,63})\}\}',raw)
        if match:out.append({'kind':match[1],'key':match[2],'line':token.map[0]})
    return out


def preview(db,value,photo_bytes=None,rule_layers=()):
    photo_bytes=photo_bytes or {};issues=[];contexts={};mapped_records=[]
    media={m.key:m for m in value.media};places={p.key:p for p in value.places}
    from ..archive_models import PlaceAlias,ResourceReferenceAudit
    from ..services.marked_places import find_existing
    from ..services.places import norm
    catalog={}
    for row in db.scalars(select(Place).where(Place.active.is_(True))):catalog.setdefault(norm(row.name),[]).append(row)
    aliases=set(db.scalars(select(PlaceAlias.source_id)))
    deleted=[a.value for a in db.scalars(select(ResourceReferenceAudit).where(ResourceReferenceAudit.key.like('dp:%')))]
    def issue(scope,message,level='error'):issues.append({'scope':scope,'message':message,'level':level})
    for m in value.media:
        if m.path and m.path not in photo_bytes:issue('media.'+m.key,'需上传包含该照片的完整ZIP，或明确映射现有媒体')
        if m.existing_id:
            row=db.get(MediaAsset,str(m.existing_id))
            if not row or row.deleted_at:issue('media.'+m.key,'现有媒体不存在或已删除')
    for p in value.places:
        try:place_mark(p.kind,p.name,p.existing_id)
        except ValueError:issue('places.'+p.key,'地点名称或身份不能由现有语法无损表达')
        if p.existing_id:
            row=db.get(Place,str(p.existing_id))
            if not row or not row.active:issue('places.'+p.key,'地点不存在或已停用，请明确选择有效身份')
    for r in value.records:
        scope='records.'+r.key;warnings=[]
        try:
            ctx=context(db,r.type_slug,r.template_slug,(*rule_layers,value.preferences));contexts[r.key]=ctx
            t=ctx['type'];template=ctx['template']
            if r.schema_version is not None and r.schema_version!=t['version']:raise HTTPException(409,'字段版本已变化，请映射当前版本并重新预览')
            if r.template_version is not None and (template is None or template['version']!=r.template_version):raise HTTPException(409,'模板版本已变化，请重新预览')
            # The provider/offline schema deliberately omits private defaults.
            # Apply actual defaults only locally against the immutable DB schema,
            # never treat that redacted export as the authoritative value schema.
            from ..services.content import fields_for
            actual_fields=fields_for(db,t['id'],t['version'])
            values,mapping=field_values(actual_fields,r.values)
            if not r.title.strip():issue(scope+'.title','标题不能为空')
            if r.display_date is None:issue(scope+'.display_date','请明确选择文章展示日期；不把旅行结束或用餐日期当作发布日期')
            for f in t['fields']:
                if f['active'] and f['required'] and values.get(f['id']) in (None,'',[]):issue(scope+'.values.'+f['id'],'必填字段尚待补充，草稿可保留空值：'+f['name'],'warning')
            normalized_tags=[normalize(tag)[1] for tag in r.tags]
            if len(set(normalized_tags))!=len(normalized_tags):issue(scope+'.tags','标签按现有归一规则重复，请明确保留一个名称')
            allowed_places={str(p.existing_id) for p in value.places if p.existing_id}
            # Existing-parser compatibility: fail explicitly rather than silently
            # creating places from escaped literal examples in newly imported text.
            parsed=marks(r.body)
            if {m['place_id'] for m in parsed.marks if m.get('place_id')}-allowed_places:issue(scope+'.body','正文地点UUID未在清单中明确声明，请映射地点身份')
            parsed_places=[]
            for mark in parsed.marks:
                existing=db.get(Place,mark['place_id']) if mark.get('place_id') else find_existing(mark,catalog,aliases,deleted)
                parsed_places.append({'kind':mark['kind'],'name':mark['name'],'region':mark['region'],'action':'reuse' if existing else 'create','city':existing.city if existing else mark['region']})
            lines=r.body.splitlines()
            for mark in parsed.marks:
                if re.search(r'(?<!\\)(?:\\\\)*\\@[lfshtcp]',lines[mark['line']-1]):
                    issue(scope+'.body','转义@标记与旧解析器存在歧义，请将字面示例置于代码格式后重新预览');break
            allowed={str(m.existing_id) for m in value.media if m.existing_id}
            cards=entries(r.body)
            if {e['fields']['place_id'] for e in cards if e['fields'].get('place_id')}-allowed_places:issue(scope+'.body','卡片地点未在清单中明确授权')
            body_ids={m['id'] for m in blocks(r.body,2)}|markdown_media_ids(r.body)|{mid for e in cards for mid in e['media_ids']}
            if body_ids-allowed:issue(scope+'.body','正文UUID未由媒体清单明确授权，不能猜测媒体身份')
            for field in t['fields']:
                field_value=values.get(field['id'])
                if field['kind']=='markdown' and isinstance(field_value,str) and markdown_media_ids(field_value)-allowed:
                    issue(scope+'.values.'+field['id'],'Markdown字段引用的媒体未在清单中明确授权')
            for ref in placeholders(r.body):
                if ref['key'] not in (media if ref['kind']=='media' else places):issue(scope+'.body','正文占位符引用不存在')
            for link in r.links:
                if link.existing_id:
                    target=db.get(ContentRecord,str(link.existing_id))
                    if not target or target.deleted_at:issue(scope+'.links','关联文章不存在或已进入回收站')
            pref=ctx['rules']['preferences']
            for flag,key,label in [('require_start','start_date','旅行开始日期'),('require_end','end_date','旅行结束日期')]:
                if pref[flag] and (r.travel is None or getattr(r.travel,key) is None):issue(scope+'.travel.'+key,label+'尚待填写，不能由AI编造','warning')
            mapped_records.append({'key':r.key,'type_id':t['id'],'schema_version':t['version'],'template':template,'title':r.title,
                                   'display_date':r.display_date.isoformat() if r.display_date else None,'status':'draft','values':values,'field_mapping':mapping,
                                   'body':r.body,'summary':r.summary,'parsed_places':parsed_places,'travel':r.travel.model_dump(mode='json') if r.travel else None,
                                   'foods':[f.model_dump(mode='json') for f in r.foods],'tags':r.tags,'context_digest':ctx['context_digest']})
        except HTTPException as error:issue(scope,str(error.detail))
    return {'valid':not any(x['level']=='error' for x in issues),'issues':issues,'records':mapped_records,
            'contexts':contexts,'format_version':1,'creates_only_drafts':True,'preview_has_no_persistent_content':True}
