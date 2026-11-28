"""Admin-only exchange inspection/spec export; confirmation uses a separate gate."""
import base64,io
from fastapi import APIRouter,Depends,UploadFile,File,Header,HTTPException
from fastapi.responses import StreamingResponse
from pydantic import Field,ValidationError
from starlette.concurrency import run_in_threadpool
from ..dependencies import require_dynamic_blog,db_dep
from ..archive_schemas import StrictModel
from ..exchange.context import context,specification_zip
from ..exchange.parsers import parse,package,MAX_PACKAGE,MAX_TEXT
from ..exchange.preview import preview
from ..services.image_upload import prepare_image

router=APIRouter(prefix='/api/admin/exchange',dependencies=[Depends(require_dynamic_blog)])
class SpecificationIn(StrictModel):
    type_slug:str=Field(pattern=r'^[a-z][a-z0-9_-]{0,79}$')
    template_slug:str|None=Field(None,pattern=r'^[a-z][a-z0-9_-]{0,79}$')

@router.post('/specification')
def export(data:SpecificationIn,db=Depends(db_dep)):
    value=context(db,data.type_slug,data.template_slug)
    return StreamingResponse(io.BytesIO(specification_zip(value)),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="life-journal-writing-spec.zip"','Cache-Control':'no-store'})

@router.post('/inspect')
async def inspect(file:UploadFile=File(...),db=Depends(db_dep)):
    name=file.filename or ''
    limit=MAX_PACKAGE if name.lower().endswith('.zip') else MAX_TEXT
    raw=await file.read(limit+1)
    if len(raw)>limit:raise HTTPException(413,'导入文件大小超限')
    return await run_in_threadpool(inspect_payload,raw,name,db)


def inspect_payload(raw,name,db):
    try:
        if name.lower().endswith('.zip'):value,photos=package(raw)
        else:value=parse(raw,name);photos={}
    except ValidationError as error:
        errors=[{k:e[k] for k in ('loc','msg','type') if k in e} for e in error.errors()]
        raise HTTPException(422,{'message':'交换字段无效；格式版本仅支持1，请核对导出规范','errors':errors}) from None
    except (ValueError,TypeError,RecursionError):raise HTTPException(422,'交换包格式或路径无效；Manifest和交换格式版本仅支持1，请核对导出规范') from None
    images=[]
    for m in value.media:
        if m.path and m.path in photos:
            variants,metadata=prepare_image(photos[m.path],m.path)
            images.append({'key':m.key,'mime_type':'image/webp','thumbnail_base64':base64.b64encode(variants['thumbnail.webp']).decode(),
                           'width':metadata['width'],'height':metadata['height'],'captured_on':metadata['captured_on'].isoformat() if metadata['captured_on'] else None,
                           'original_preserved':True,'preview_strips_exif':True})
    result=preview(db,value,photos);result['images']=images
    return result


from uuid import UUID
from ..dependencies import get_settings
from ..exchange import jobs

class ConfirmIn(StrictModel):
    expected_revision:int=Field(ge=1)
    confirmation:str=Field(pattern='^创建草稿$')

class MappingIn(StrictModel):
    expected_revision:int=Field(ge=1)
    content:dict

@router.post('/preview')
async def prepare(file:UploadFile=File(...),request_key:UUID=Header(...,alias='X-Import-Key'),db=Depends(db_dep),user=Depends(require_dynamic_blog),settings=Depends(get_settings)):
    name=file.filename or '';limit=MAX_PACKAGE if name.lower().endswith('.zip') else MAX_TEXT
    raw=await file.read(limit+1)
    if len(raw)>limit:raise HTTPException(413,'导入文件大小超限')
    return await run_in_threadpool(jobs.stage,db,user.id,settings.media_dir,raw,name,request_key)

@router.get('/jobs/{id}')
def read_job(id:UUID,db=Depends(db_dep),user=Depends(require_dynamic_blog)):
    return jobs.public(db,jobs.get_job(db,id,user.id))

class RevisionIn(StrictModel):
    expected_revision:int=Field(ge=1)

@router.put('/jobs/{id}/mapping')
def map_job(id:UUID,data:MappingIn,db=Depends(db_dep),user=Depends(require_dynamic_blog)):
    try:return jobs.remap(db,id,user.id,data.content,data.expected_revision)
    except ValidationError as error:
        raise HTTPException(422,{'message':'映射字段无效','errors':[{k:e[k] for k in ('loc','msg','type') if k in e} for e in error.errors()]}) from None

@router.post('/jobs/{id}/cancel')
def cancel_job(id:UUID,data:RevisionIn,db=Depends(db_dep),user=Depends(require_dynamic_blog)):
    return jobs.cancel(db,id,user.id,data.expected_revision)

@router.post('/jobs/{id}/confirm')
def confirm_job(id:UUID,data:ConfirmIn,db=Depends(db_dep),user=Depends(require_dynamic_blog),settings=Depends(get_settings)):
    try:return jobs.confirm(db,id,user.id,settings.media_dir,data.expected_revision)
    except HTTPException:raise
    except Exception:raise HTTPException(503,'确认导入失败，状态和文件日志已保留；请读取原任务后重试') from None

@router.get('/jobs/{id}/images/{media_id}')
def staged_image(id:UUID,media_id:UUID,db=Depends(db_dep),user=Depends(require_dynamic_blog),settings=Depends(get_settings)):
    from fastapi.responses import Response,RedirectResponse
    from ..archive_models import MediaAsset
    row=jobs.get_job(db,id,user.id)
    entries=[x for x in row.file_manifest['media'].values() if x['id']==str(media_id)]
    if len(entries)!=1 or row.state=='cancelled':raise HTTPException(404,'预览图片不存在')
    if row.state=='completed':
        asset=db.get(MediaAsset,str(media_id))
        if not asset or asset.deleted_at:raise HTTPException(404,'媒体不可用')
        return RedirectResponse('/api/library-media/'+str(media_id)+'/thumbnail')
    from ..models import now
    from datetime import timezone
    expires=row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if expires<now():raise HTTPException(410,'预览已过期')
    try:
        path=jobs.stage_dir(settings.media_dir,str(id),str(media_id));jobs.verify_files(path,entries[0]['files']);data=(path/'thumbnail.webp').read_bytes()
    except OSError:raise HTTPException(409,'预览文件状态已变化，请重新读取任务') from None
    return Response(data,media_type='image/webp',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


from ..exchange.settings import Configuration,read as read_configuration,save as save_configuration
class ConfigurationIn(Configuration):
    expected_revision:int=Field(ge=0,strict=True)

@router.get('/settings')
def settings_read(db=Depends(db_dep)):
    revision,value=read_configuration(db)
    return {'revision':revision,**value.model_dump(mode='json')}

@router.put('/settings')
def settings_save(data:ConfigurationIn,db=Depends(db_dep)):
    value=Configuration.model_validate(data.model_dump(exclude={'expected_revision'}))
    return save_configuration(db,value,data.expected_revision)


from ..exchange import invocations
@router.post('/ai/generate')
def generate_text(data:invocations.GenerateIn,db=Depends(db_dep),user=Depends(require_dynamic_blog),settings=Depends(get_settings)):
    return invocations.generate(db,user.id,settings.media_dir,data)

@router.get('/ai/calls')
def calls(db=Depends(db_dep),user=Depends(require_dynamic_blog)):
    from sqlalchemy import select
    from ..exchange.models import AIInvocation
    rows=db.scalars(select(AIInvocation).where(AIInvocation.actor_id==user.id).order_by(AIInvocation.created_at.desc(),AIInvocation.id.desc()).limit(50))
    return {'items':[invocations.status(db,row,include_preview=False) for row in rows]}

@router.get('/ai/calls/{id}')
def call_status(id:UUID,db=Depends(db_dep),user=Depends(require_dynamic_blog)):
    return invocations.status(db,invocations.owned(db,id,user.id))

@router.post('/ai/calls/{id}/cancel')
def cancel_call(id:UUID,db=Depends(db_dep),user=Depends(require_dynamic_blog)):
    return invocations.cancel(db,id,user.id)


@router.get('/ai/requests/{request_key}')
def request_status(request_key:UUID,db=Depends(db_dep),user=Depends(require_dynamic_blog)):
    from sqlalchemy import select
    from ..exchange.models import AIInvocation
    row=db.scalar(select(AIInvocation).where(AIInvocation.actor_id==user.id,AIInvocation.request_key==str(request_key)))
    if row is None:raise HTTPException(404,'模型请求尚未登记，请稍后核对')
    return invocations.status(db,row,include_preview=False)


class AbandonIn(StrictModel):
    confirmation:str=Field(pattern='^确认状态未知$')

@router.post('/ai/calls/{id}/abandon')
def abandon_call(id:UUID,data:AbandonIn,db=Depends(db_dep),user=Depends(require_dynamic_blog)):
    return invocations.abandon(db,id,user.id)


@router.get('/ai/presets')
def ai_presets():
    from ..exchange.presets import PRESETS
    from ..exchange.settings import TASKS
    return {'items':PRESETS,'tasks':list(TASKS),'streaming':False}


@router.get('/ai/services/{id}/models')
def service_models(id:UUID,expected_revision:int,db=Depends(db_dep)):
    from ..exchange import adapters,transport
    revision,config=read_configuration(db)
    if expected_revision!=revision:raise HTTPException(409,'服务商配置已变化，请重新读取')
    service=next((s for s in config.services if s.id==id and s.enabled),None)
    if service is None:raise HTTPException(422,'请选择已保存并启用的服务商；不支持列表时可手动添加模型')
    try:
        value=transport.get(service,adapters.models_path(service))
        return {'items':adapters.models(service,value),'possibly_incomplete':True,'notice':'仅显示服务返回的首批模型；可手动添加，能力需自行核对。'}
    except (ValueError,KeyError,TypeError):raise HTTPException(502,'模型列表响应格式无效；仍可手动添加模型') from None
