import uuid
from uuid import UUID
from datetime import date,timedelta
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import select,update
from ..dependencies import db_dep,current_user,require_dynamic_blog
from ..content_models import ContentRecord
from ..services.archive import write_lock
from ..services.blog import save_config
from ..content_schemas import StrictModel
from typing import Literal
from .models import Anniversary,Reminder
from .schemas import EventIn,NotifyConfig
from .dates import DateRule,occurrences
from .service import today,list_events,memories,config,KEY
from .transport import template,resolve,render,get,deliver,DeliveryError
from urllib.parse import urlsplit
router=APIRouter(prefix='/api/calendar',dependencies=[Depends(current_user)])
admin=APIRouter(prefix='/api/admin/calendar',dependencies=[Depends(require_dynamic_blog)])

def event(db,id):
    e=db.get(Anniversary,str(id))
    if not e or not e.active:raise HTTPException(404,'纪念日不存在')
    return e

@router.get('')
def listing(start:date|None=None,end:date|None=None,db=Depends(db_dep)):
    start=start or today(db)
    try:end=end or start+timedelta(days=366)
    except OverflowError:raise HTTPException(422,'日历查询超出有效日期范围') from None
    if end<start or (end-start).days>366:raise HTTPException(422,'日历查询范围须为0–366天')
    return {'items':list_events(db,start,end),'today':today(db).isoformat()}

@router.get('/{id}')
def detail(id:UUID,memory_page:int=Query(1,ge=1,le=100000),db=Depends(db_dep)):
    e=event(db,id);day=today(db)
    return {'id':e.id,'name':e.name,'kind':e.kind,'rule':e.rule,'upcoming':list_events_for(e,day),**memories(db,e,memory_page)}

def list_events_for(e,day):return [d.isoformat() for d in occurrences(DateRule.model_validate(e.rule),day,day+timedelta(days=min(366*8,(date.max-day).days)))][:24]

@admin.get('/events')
def events(db=Depends(db_dep)):
    return [{'id':e.id,'name':e.name,'kind':e.kind,'rule':e.rule,'reminders':e.reminders,'memories':e.memories,'expected_revision':e.revision} for e in db.scalars(select(Anniversary).where(Anniversary.active.is_(True)).order_by(Anniversary.name,Anniversary.id))]

def save(db,d,e=None):
    write_lock(db)
    if (e.revision if e else 0)!=d.expected_revision:raise HTTPException(409,'纪念日已被修改，请重新读取')
    mids=[str(x) for x in d.memories]
    if set(mids)!=set(db.scalars(select(ContentRecord.id).where(ContentRecord.id.in_(mids),ContentRecord.deleted_at.is_(None)))):raise HTTPException(422,'专属回忆文章不存在')
    if not e:e=Anniversary(id=str(uuid.uuid4()),revision=0);db.add(e)
    e.name=d.name.strip();e.kind=d.kind;e.rule=d.rule.model_dump();e.reminders=d.reminders.model_dump();e.memories=mids;e.active=True;e.revision+=1
    db.commit();return {'id':e.id,'revision':e.revision}

@admin.post('/events')
def create(d:EventIn,db=Depends(db_dep)):return save(db,d)
@admin.put('/events/{id}')
def edit(id:UUID,d:EventIn,db=Depends(db_dep)):
    write_lock(db);return save(db,d,event(db,id))
@admin.delete('/events/{id}')
def remove(id:UUID,expected_revision:int=Query(ge=1),db=Depends(db_dep)):
    write_lock(db);e=event(db,id)
    if e.revision!=expected_revision:raise HTTPException(409,'纪念日已被修改')
    e.active=False;e.revision+=1
    db.execute(update(Reminder).where(Reminder.anniversary_id==e.id,Reminder.state.in_(['queued','retry'])).values(state='cancelled',error='event_deleted'));db.commit();return {'ok':True}

@admin.get('/notification')
def notification(db=Depends(db_dep)):
    rev,c=config(db);return c|{'expected_revision':rev}
@admin.put('/notification')
def configure(d:NotifyConfig,db=Depends(db_dep)):
    if d.url_template:
        try:template(d.url_template)
        except ValueError:raise HTTPException(422,'通知URL模板无效，变量仅支持路径或查询参数值') from None
    if d.enabled:
        try:resolve(urlsplit(d.url_template))
        except DeliveryError as e:raise HTTPException(422,'通知目标校验失败：'+e.code) from None
    write_lock(db);rev,current=config(db);candidate=d.model_dump(exclude={'expected_revision'})
    if rev!=d.expected_revision:raise HTTPException(409,'通知设置已被修改，请重新读取')
    if current==candidate:return {'ok':True,'revision':rev,'unchanged':True}
    save_config(db,KEY,candidate,d.expected_revision);db.commit();return {'ok':True,'revision':d.expected_revision+1}
@admin.post('/notification/test')
def test_notification(db=Depends(db_dep)):
    _,c=config(db)
    try:
        template(c['url_template']);status=deliver(c,{'title':'测试通知','content':'Life Journal 测试，不代表终端设备已收到','name':'测试','date':today(db).isoformat(),'days_left':0,'years':0,'calendar_type':'solar'},legacy_get=get)
        return {'http_status':status,'state':'sent','note':'HTTP 2xx只表示接口成功，不代表平台业务成功或终端收到推送'}
    except DeliveryError as exc:return {'state':'uncertain' if exc.uncertain else 'failed','note':'通知未确认成功，请先核对外部结果再决定重试；未返回URL或凭据'}
    except ValueError:return {'state':'failed','note':'通知配置无效；未返回URL或凭据'}

@admin.get('/logs')
def logs(page:int=Query(1,ge=1,le=100000),db=Depends(db_dep)):
    return [{'id':r.id,'name':e.name,'anniversary_id':e.id,'occurrence':r.occurrence,'offset':r.offset,'channel':r.channel,'state':r.state,'planned_at':r.planned_at,'attempted_at':r.attempted_at,'sent_at':r.sent_at,'attempts':r.attempts,'http_status':r.http_status,'error':r.error} for r,e in db.execute(select(Reminder,Anniversary).join(Anniversary,Anniversary.id==Reminder.anniversary_id).order_by(Reminder.planned_at.desc(),Reminder.id).offset((page-1)*50).limit(50))]
class Retry(StrictModel):
    confirmation:Literal['我已核对外部发送结果并接受重复通知风险']
@admin.post('/logs/{id}/retry')
def retry(id:UUID,d:Retry,db=Depends(db_dep)):
    write_lock(db);r=db.get(Reminder,str(id))
    if not r or r.state not in ('failed','uncertain'):raise HTTPException(409,'仅失败或不确定节点可由管理员核对后重试')
    event(db,r.anniversary_id)
    r.state='queued';r.retry_at=None;r.error='manual_retry_after_review';db.commit();return {'ok':True}

@admin.get('/events/{id}/schedule')
def schedule(id:UUID,db=Depends(db_dep)):
    from datetime import datetime,time,timezone
    from zoneinfo import ZoneInfo
    e=event(db,id);_,c=config(db);d=e.reminders
    if not d.get('enabled',True):return {'items':[],'timezone':c['timezone']}
    zone=ZoneInfo(c['timezone']);now=datetime.now(timezone.utc);out=[]
    for value in list_events_for(e,today(db)):
        day=date.fromisoformat(value)
        for offset in [*d.get('offsets',[]),*([0] if d.get('on_day',True) else [])]:
            planned=datetime.combine(day-timedelta(days=offset),time.fromisoformat(d.get('time') or c['time']),zone)
            if planned>=now:out.append({'occurrence':value,'offset':offset,'planned_at':planned.isoformat()})
    return {'items':sorted(out,key=lambda x:x['planned_at'])[:48],'timezone':c['timezone'],'channel_enabled':c['enabled']}


@admin.post('/notification/preview')
def preview_notification(d:NotifyConfig):
    from .request_templates import preview
    try:return preview(d.model_dump(exclude={'expected_revision'}),{'title':'合成纪念日','content':'合成通知内容','name':'合成名称','date':'2030-01-01','days_left':3,'years':1,'calendar_type':'solar'})
    except (ValueError,TypeError,RecursionError,UnicodeError):raise HTTPException(422,'通知请求模板无法安全解析') from None
