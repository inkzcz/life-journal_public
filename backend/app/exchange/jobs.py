"""Durable preview staging and caller-owned, idempotent draft import transactions.

Only server-allocated UUID directories belong to this journal. Existing shared
media is never renamed, overwritten or removed. Uncertain commits fail closed.
"""
import hashlib,json,os,uuid
from datetime import timedelta,timezone,date
from pathlib import Path
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from ..models import now
from ..archive_models import MediaAsset,Place,ResourceReferenceAudit
from ..content_schemas import RecordCreate
from ..services.archive import write_lock,replace_connections
from ..services.uploads import upload_lock,directory
from ..services.write_barrier import writer
from ..services.image_upload import prepare_image
from ..services.media_recovery import fsync_dir
from ..services.content import create_record_in_transaction,revision_snapshot
from ..services.places import norm,canonical
from ..services.tags import identity
from .models import ExchangeJob,ExchangeFileOperation
from .schemas import Exchange
from .parsers import parse,package
from .preview import preview
from .assemble import compile_record

NAMES={'original','preview.webp','thumbnail.webp'}

def digest(data):return hashlib.sha256(data).hexdigest()
def checkpoint(stage):pass  # Test-only failure seam, never an environment bypass.
def payload_digest(value):return digest(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())

def get_job(db,id,actor,lock=False):
    row=db.scalar(select(ExchangeJob).where(ExchangeJob.id==str(id)).with_for_update() if lock else select(ExchangeJob).where(ExchangeJob.id==str(id)))
    if row is None or row.actor_id!=actor:raise HTTPException(404,'导入任务不存在')
    return row


def checked(path):
    path=Path(path)
    if any(p.is_symlink() for p in (path,*path.parents)):raise HTTPException(409,'导入文件路径状态异常，已停止')
    return path


def stage_dir(root,job,id):return checked(Path(root)/'.exchange-v1'/str(uuid.UUID(str(job)))/str(uuid.UUID(str(id))))
def library_dir(root,id):return checked(Path(root)/'library-v1'/str(uuid.UUID(str(id))))


def verify_files(path,files):
    path=checked(path)
    if set(files)!=NAMES or any(not isinstance(s,str) or len(s)!=64 or any(c not in '0123456789abcdef' for c in s) for s in files.values()):raise HTTPException(409,'导入文件日志字段无效')
    if not path.is_dir() or {p.name for p in path.iterdir()}!=set(files):raise HTTPException(409,'导入文件清单不完整；请使用同一任务重新预览，不会删除未知文件')
    for name,sha in files.items():
        p=checked(path/name)
        if not p.is_file() or digest(p.read_bytes())!=sha:raise HTTPException(409,'导入文件完整性校验失败，停止确认')


def stage(db,actor,root,raw,name,request_key):
    try:
        request_key=str(uuid.UUID(str(request_key)))
        value,photos=package(raw) if name.lower().endswith('.zip') else (parse(raw,name),{})
    except ValidationError as error:raise HTTPException(422,{'message':'交换字段格式无效，请按导出规范修正源文件后重新上传','errors':[{k:e[k] for k in ('loc','msg','type') if k in e} for e in error.errors()]}) from None
    except (ValueError,TypeError,RecursionError):raise HTTPException(422,'导入格式、版本或路径无效') from None
    report=preview(db,value,photos);variants={};entries={}
    for m in value.media:
        if not m.path:continue
        if m.path not in photos:continue  # Report remains invalid; user can map existing media.
        files,metadata=prepare_image(photos[m.path],m.path)
        metadata={k:v.isoformat() if isinstance(v,date) else v for k,v in metadata.items()}
        variants[m.key]=files;entries[m.key]={'id':str(uuid.uuid4()),'path':m.path,'metadata':metadata,'files':{k:digest(v) for k,v in files.items()}}
    with writer(db.bind),upload_lock(db):
        write_lock(db)
        row=db.scalar(select(ExchangeJob).where(ExchangeJob.actor_id==actor,ExchangeJob.request_key==request_key).with_for_update())
        if row:
            if row.source_sha256!=digest(raw):raise HTTPException(409,'相同预览请求标识不能用于不同文件')
            if row.state=='completed':return public(db,row)
            entries=row.file_manifest['media']
            if row.state=='failed':
                operation=db.get(ExchangeFileOperation,row.id)
                if not operation or operation.state!='rolled_back' or any(db.get(MediaAsset,e['id']) is not None or library_dir(root,e['id']).exists() for e in entries.values()):
                    raise HTTPException(409,'失败任务的提交状态尚未核对，保留全部文件，请先继续原确认任务')
                row.state='preview';row.error_code='';row.revision+=1;db.commit()
            elif row.state!='preview':raise HTTPException(409,'任务已进入确认或取消状态，请继续原任务')
        else:
            count=db.scalar(select(func.count()).select_from(ExchangeJob).where(ExchangeJob.actor_id==actor,ExchangeJob.state.in_(['preview','confirming']),ExchangeJob.expires_at>now()))
            if count>=50:raise HTTPException(429,'未完成预览过多，请先确认或取消原任务')
            row=ExchangeJob(id=str(uuid.uuid4()),actor_id=actor,request_key=request_key,source_sha256=digest(raw),source_kind='zip' if name.lower().endswith('.zip') else 'text',
                state='preview',revision=1,payload=value.model_dump(mode='json'),context_digests={k:c['context_digest'] for k,c in report['contexts'].items()},
                file_manifest={'media':entries,'record_ids':{r.key:str(uuid.uuid4()) for r in value.records}},result_ids=[],error_code='',expires_at=now()+timedelta(hours=24))
            db.add(row);db.commit()  # Durable owner/manifest exists BEFORE staging files.
        for key,entry in entries.items():
            target=directory(Path(root),'.exchange-v1',row.id,entry['id'])
            files=variants.get(key)
            if files is None:raise HTTPException(409,'原预览照片缺失，请重试同一文件')
            if {k:digest(v) for k,v in files.items()}!=entry['files']:raise HTTPException(409,'重试文件内容与原预览不一致')
            for filename,data in files.items():
                p=checked(target/filename)
                if p.exists():
                    if not p.is_file() or digest(p.read_bytes())!=entry['files'][filename]:raise HTTPException(409,'临时文件发生变化，停止覆盖')
                else:
                    with p.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
            fsync_dir(target);verify_files(target,entry['files'])
        return public(db,row)


def public(db,row):
    value=Exchange.model_validate(row.payload)
    expires=row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    expired=expires<now() and row.state!='completed'
    result=preview(db,value,{m.path:b'' for m in value.media if m.path})
    result['stale_context']={k:c['context_digest'] for k,c in result['contexts'].items()}!=row.context_digests
    if result['stale_context'] and row.state!='completed':
        result['valid']=False;result['issues'].append({'scope':'context','level':'error','message':'字段、模板或规则已变化，请重新映射并预览'})
    if expired:
        result['valid']=False;result['issues'].append({'scope':'expiry','level':'error','message':'预览已过期，请重新选择源文件并生成新预览；旧文章未修改'})
    if result['valid']:
        try:
            entries=row.file_manifest['media'];mids={m.key:str(m.existing_id) if m.existing_id else entries[m.key]['id'] for m in value.media}
            planned=[];pids=place_plan(db,value,details=planned);result['planned_places']=planned
            for r in value.records:
                compiled=compile_record(r,value,mids,pids,row.file_manifest['record_ids'][r.key])
                item=next(x for x in result['records'] if x['key']==r.key)
                item['compiled_body']=compiled['body'];item['compiled_life']=compiled['life']
        except HTTPException as error:
            result['valid']=False;result['issues'].append({'scope':'compilation','level':'error','message':str(error.detail)})
    images=[{'id':entry['id'],'key':key,'url':'/api/admin/exchange/jobs/'+row.id+'/images/'+entry['id'],'width':entry['metadata']['width'],'height':entry['metadata']['height']} for key,entry in row.file_manifest['media'].items() if any(m.key==key and m.path for m in value.media)]
    for media in value.media:
        if not media.existing_id:continue
        asset=db.get(MediaAsset,str(media.existing_id))
        if asset and not asset.deleted_at:images.append({'id':asset.id,'key':media.key,'url':'/api/library-media/'+asset.id+'/thumbnail','width':asset.width,'height':asset.height})
    result.update({'id':row.id,'revision':row.revision,'state':row.state,'result_ids':row.result_ids,'error_code':row.error_code,'input':row.payload,'expires_at':expires.isoformat(),'expired':expired,'images':[] if expired or row.state=='cancelled' else images,'source_media':[{'key':key,'path':entry['path']} for key,entry in row.file_manifest['media'].items()]})
    return result


def remap(db,id,actor,content,expected_revision):
    """Re-preview explicit user mappings; never allocate or replace photo bytes."""
    value=Exchange.model_validate(content)
    with writer(db.bind),upload_lock(db):
        write_lock(db);row=get_job(db,id,actor,lock=True)
        if row.state not in {'preview','failed'}:raise HTTPException(409,'任务状态不允许修改映射')
        if row.revision!=expected_revision:raise HTTPException(409,'预览已更新，请重新读取')
        expires=row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
        if expires<now():raise HTTPException(410,'预览已过期，请重新上传')
        old=Exchange.model_validate(row.payload)
        if {r.key for r in value.records}!={r.key for r in old.records}:raise HTTPException(422,'映射不得新增或替换文章身份，请建立新预览')
        entries=row.file_manifest['media']
        for m in value.media:
            if m.path and (m.key not in entries or entries[m.key]['path']!=m.path):
                raise HTTPException(422,'映射不得替换已校验照片路径或身份，请重新上传完整包')
        report=preview(db,value,{m.path:b'' for m in value.media if m.path})
        row.payload=value.model_dump(mode='json')
        row.context_digests={k:c['context_digest'] for k,c in report['contexts'].items()}
        row.revision+=1;row.state='preview';row.error_code=''
        # A rolled-back operation is retained as an audit record until the next
        # explicit confirmation replaces its payload-bound manifest.
        db.commit()
        return public(db,row)


def cancel(db,id,actor,expected_revision):
    with writer(db.bind),upload_lock(db):
        write_lock(db);row=get_job(db,id,actor,lock=True)
        if row.state=='cancelled':return {'id':row.id,'state':'cancelled','revision':row.revision}
        if row.state not in {'preview','failed'}:raise HTTPException(409,'任务状态不允许取消，请核对确认结果')
        if row.revision!=expected_revision:raise HTTPException(409,'预览已更新，请重新读取')
        row.state='cancelled';row.revision+=1;db.commit()
        # No library files or records are deleted. Staging remains journal-owned
        # for explicit maintenance cleanup, not a hidden destructive cascade.
        return {'id':row.id,'state':row.state,'revision':row.revision}


def place_plan(db,value,*,create=False,details=None):
    from ..services.marked_places import KINDS,find_existing
    from ..archive_models import PlaceAlias
    result={};catalog={};new_ids=set()
    for item in db.scalars(select(Place).where(Place.active.is_(True))):catalog.setdefault(norm(item.name),[]).append(item)
    aliases=set(db.scalars(select(PlaceAlias.source_id)))
    deleted=[a.value for a in db.scalars(select(ResourceReferenceAudit).where(ResourceReferenceAudit.key.like('dp:%')))]
    for p in value.places:
        if p.existing_id:
            row=db.get(Place,canonical(db,str(p.existing_id)))
            if not row or not row.active:raise HTTPException(422,'选择的地点不存在或已停用')
        else:
            row=find_existing({'name':p.name,'kind':p.kind,'region':p.city},catalog,aliases,deleted,p.address)
            if row is None:
                row=Place(id=str(uuid.uuid4()),name=p.name,city=p.city,address=p.address,category=KINDS[p.kind],country='',region='',notes='',active=True,revision=1)
                if create:db.add(row);db.flush()
                catalog.setdefault(norm(row.name),[]).append(row);new_ids.add(row.id)
        result[p.key]=row.id
        if details is not None:details.append({'key':p.key,'action':'create' if row.id in new_ids else 'reuse','existing_id':None if row.id in new_ids else row.id,'name':row.name,'city':row.city,'region':row.region,'address':row.address,'category':row.category})
    return result


def confirm(db,id,actor,root,expected_revision):
    root=Path(root)
    with writer(db.bind),upload_lock(db):
        write_lock(db);row=get_job(db,id,actor,lock=True)
        if row.state=='completed':
            finished=db.get(ExchangeFileOperation,row.id)
            if finished and finished.state=='db_committed':finished.state='completed';db.commit()
            return public(db,row)|{'replayed':True}
        if row.state=='cancelled':raise HTTPException(409,'任务已取消')
        expires=row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
        if expires<now():raise HTTPException(410,'预览已过期，请重新预览')
        op=db.get(ExchangeFileOperation,row.id)
        if row.revision!=expected_revision and not(op and op.manifest.get('expected_revision')==expected_revision and op.manifest.get('payload_digest')==payload_digest(row.payload)):
            raise HTTPException(409,'预览已更新，请重新读取后确认')
        value=Exchange.model_validate(row.payload);report=preview(db,value,{m.path:b'' for m in value.media if m.path})
        if not report['valid']:raise HTTPException(422,{'message':'请先修正预览中的问题','issues':report['issues']})
        current={k:c['context_digest'] for k,c in report['contexts'].items()}
        if current!=row.context_digests:raise HTTPException(409,'字段、模板或规则已变化，请重新预览确认')
        entries={key:row.file_manifest['media'][key] for key in [m.key for m in value.media if m.path]};mids={m.key:str(m.existing_id) if m.existing_id else entries[m.key]['id'] for m in value.media}
        pids=place_plan(db,value)
        # Compile/round-trip before any permanent file placement.
        for r in value.records:compile_record(r,value,mids,pids,row.file_manifest['record_ids'][r.key],set(e['id'] for e in entries.values()))
        if op is None:
            op=ExchangeFileOperation(job_id=row.id,state='prepared',manifest={'media':entries,'expected_revision':expected_revision,'payload_digest':payload_digest(row.payload)})
            db.add(op)
        else:
            op.manifest={'media':entries,'expected_revision':expected_revision,'payload_digest':payload_digest(row.payload)}
            op.state='prepared'
        row.state='confirming';row.revision+=1;db.commit()
        try:
            for entry in entries.values():
                source=stage_dir(root,row.id,entry['id']);target=library_dir(root,entry['id'])
                directory(root,'library-v1')
                if target.exists():verify_files(target,entry['files'])
                else:verify_files(source,entry['files']);os.rename(source,target);fsync_dir(target.parent);fsync_dir(source.parent)
            checkpoint('files_ready')
            write_lock(db);db.expire_all();row=get_job(db,id,actor,lock=True);op=db.get(ExchangeFileOperation,row.id)
            # Fence final indexes against a recovery attempt: after taking the
            # archive transaction lock, every permanent file must still exist.
            for entry in entries.values():verify_files(library_dir(root,entry['id']),entry['files'])
            # The prepared commit released the archive transaction lock while
            # moving files. A different administrator may have changed schemas
            # or rules in that interval. Revalidate under the FINAL write lock.
            report=preview(db,value,{m.path:b'' for m in value.media if m.path})
            if not report['valid']:raise HTTPException(422,{'message':'确认期间资源或字段已变化，请重新映射','issues':report['issues']})
            if {k:c['context_digest'] for k,c in report['contexts'].items()}!=current:
                raise HTTPException(409,'确认期间字段、模板或规则已变化，文件已保留，请重新映射预览')
            op.state='files_ready';pids=place_plan(db,value,create=True)
            for entry in entries.values():
                old=db.get(MediaAsset,entry['id'])
                if old is not None:raise HTTPException(409,'媒体身份已存在且任务未完成，停止重复写入')
                metadata=dict(entry['metadata'])
                if metadata.get('captured_on'):metadata['captured_on']=date.fromisoformat(metadata['captured_on'])
                db.add(MediaAsset(id=entry['id'],uploaded_by=actor,**metadata))
            db.flush();created=[];compiled={};new_ids={e['id'] for e in entries.values()}
            for r in value.records:
                ctx=report['contexts'][r.key];compiled[r.key]=c=compile_record(r,value,mids,pids,row.file_manifest['record_ids'][r.key],new_ids)
                base=next(x for x in report['records'] if x['key']==r.key)
                data=RecordCreate(type_id=ctx['type']['id'],schema_version=ctx['type']['version'],template={'id':ctx['template']['id'],'version':ctx['template']['version']} if ctx['template'] else None,
                    title=r.title,body=c['body'],summary=r.summary,body_format=2,display_date=r.display_date,status='draft',values=base['values'],
                    connections=c['connections'],life=c['life'],new_media_ids=c['new_media_ids'],tag_ids=[identity(db,n).id for n in r.tags])
                obj=create_record_in_transaction(db,data,actor,snapshot=False,record_id=row.file_manifest['record_ids'][r.key])
                created.append((r,obj))
                new_ids-=set(c['new_media_ids'])
            checkpoint('records_created')
            from ..archive_schemas import Connections
            from ..life_models import TripActivity
            from ..services.itinerary_generation import record_audit
            actual_ids={r.key:obj.id for r,obj in created}
            for r,obj in created:
                c=compiled[r.key];links=[{'id':str(l.existing_id) if l.existing_id else actual_ids[l.record_key],'label':l.label} for l in r.links]
                replace_connections(db,obj,Connections.model_validate(c['connections']|{'links':links}))
                for aid in c['markdown_activity_ids']:
                    a=db.get(TripActivity,aid)
                    if a is not None:a.markdown_owned=True
                if r.travel and (r.travel.activities or r.foods):record_audit(db,obj,'generated','已确认导入结构化行程；后续重新提取需明确预览')
                revision_snapshot(db,obj,actor)
            row.state='completed';row.result_ids=[obj.id for _,obj in created];row.error_code='';op.state='db_committed';db.commit()
            checkpoint('db_committed');op.state='completed';db.commit()
            return public(db,row)|{'replayed':False}
        except Exception:
            db.rollback()
            # Hold the SAME archive transaction lock while deciding and rolling
            # files back. A different recovery's final commit cannot race this
            # check and then lose its successfully committed files.
            try:
                write_lock(db);db.expire_all();saved=get_job(db,id,actor,lock=True)
                if saved.state=='completed':
                    result=public(db,saved)|{'replayed':True};db.rollback();return result
                if any(db.get(MediaAsset,e['id']) is not None for e in entries.values()):raise HTTPException(503,'导入提交状态需要核对，保留全部文件，请重试原任务')
            except HTTPException:raise
            except Exception:raise HTTPException(503,'无法确认提交状态，保留全部文件，请重试原任务') from None
            for entry in entries.values():
                target=library_dir(root,entry['id']);source=stage_dir(root,str(id),entry['id'])
                if target.exists():
                    verify_files(target,entry['files'])
                    if source.exists():raise HTTPException(409,'导入临时目录冲突，保留文件等待核对')
                    directory(root,'.exchange-v1',str(id));os.rename(target,source);fsync_dir(target.parent);fsync_dir(source.parent)
            write_lock(db);saved=get_job(db,id,actor,lock=True);saved.state='failed';saved.error_code='confirmation_failed'
            operation=db.get(ExchangeFileOperation,str(id));operation.state='rolled_back';db.commit()
            raise
