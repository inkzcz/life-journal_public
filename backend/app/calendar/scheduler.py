"""Durable per-offset claims. Unknown external outcome is never auto-retried."""
import uuid
from datetime import datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select,update,or_
from sqlalchemy.exc import IntegrityError
from ..models import now
from ..services.archive import write_lock
from .models import Anniversary,Reminder
from .dates import DateRule,occurrences,years_at
from .service import config
from .transport import render,get,deliver,DeliveryError
UTC=timezone.utc

def aware(d):return d if d.tzinfo else d.replace(tzinfo=UTC)

def plan(db,at):
    write_lock(db);rev,c=config(db)
    if not c['enabled']:return
    zone=ZoneInfo(c['timezone']);local=at.astimezone(zone);day=local.date();channel=c.get('method','GET').lower()+':'+str(rev)
    for e in db.scalars(select(Anniversary).where(Anniversary.active.is_(True))):
        d=e.reminders
        if not d.get('enabled',True):continue
        rule=DateRule.model_validate(e.rule)
        for offset in [*d.get('offsets',[]),*([0] if d.get('on_day',True) else [])]:
            target=day+timedelta(days=offset)
            if not occurrences(rule,target,target):continue
            planned=datetime.combine(day,time.fromisoformat(d.get('time') or c['time']),zone).astimezone(UTC)
            # DST gaps move forward by the actual timezone roundtrip; overlaps
            # use fold=0 and the same unique node, so a repeated wall time can't resend.
            planned=planned.astimezone(zone).astimezone(UTC)
            if at<planned:continue
            exists=db.scalar(select(Reminder.id).where(Reminder.anniversary_id==e.id,Reminder.occurrence==target,Reminder.offset==offset,Reminder.channel==channel))
            if exists:continue
            try:
                with db.begin_nested():
                    db.add(Reminder(id=str(uuid.uuid4()),anniversary_id=e.id,occurrence=target,offset=offset,channel=channel,state='queued',planned_at=planned,sent_at=None,retry_at=None,lease_until=None,attempts=0,http_status=None,error=''));db.flush()
            except IntegrityError:pass  # Concurrent node creation has one durable winner.
    db.execute(update(Reminder).where(Reminder.state=='sending',Reminder.lease_until<at).values(state='uncertain',error='worker_interrupted'))
    db.commit()

def tick(session_factory,at=None,send=get,request_sender=None):
    at=aware(at or now())
    with session_factory() as db:plan(db,at)
    # Short claim transactions, then network OUTSIDE the write lock.
    for _ in range(3):
        with session_factory() as db:
            write_lock(db);rev,c=config(db)
            if not c['enabled']:return
            row=db.scalar(select(Reminder).where(Reminder.state.in_(['queued','retry']),or_(Reminder.retry_at.is_(None),Reminder.retry_at<=at)).order_by(Reminder.planned_at,Reminder.id).limit(1))
            if not row:return
            event=db.get(Anniversary,row.anniversary_id)
            rule=DateRule.model_validate(event.rule)
            if not occurrences(rule,row.occurrence,row.occurrence) or not event.active or row.channel!=c.get('method','GET').lower()+':'+str(rev) or not event.reminders.get('enabled',True) or row.offset==0 and not event.reminders.get('on_day',True) or row.offset>0 and row.offset not in event.reminders.get('offsets',[]):
                row.state='cancelled';row.error='configuration_changed';db.commit();continue
            planned=datetime.combine(row.occurrence-timedelta(days=row.offset),time.fromisoformat(event.reminders.get('time') or c['time']),ZoneInfo(c['timezone'])).astimezone(UTC)
            if at<planned:
                row.retry_at=planned;row.planned_at=planned;db.commit();continue
            result=db.execute(update(Reminder).where(Reminder.id==row.id,Reminder.state.in_(['queued','retry'])).values(state='sending',attempted_at=now(),attempts=Reminder.attempts+1,lease_until=at+timedelta(minutes=2)))
            if result.rowcount!=1:db.rollback();continue
            rid=row.id;offset=row.offset;occ=row.occurrence;name=event.name;rule=DateRule.model_validate(event.rule);attempts=row.attempts;db.commit()
        variables={'title':name+' · '+('今天' if offset==0 else str(offset)+'天后'),'content':name+' '+occ.isoformat(),'name':name,'date':occ.isoformat(),'days_left':offset,'years':years_at(rule,occ),'calendar_type':rule.calendar}
        state='sent';error='';status=None;retry=None
        try:status=deliver(c,variables,legacy_get=send,request_sender=request_sender)
        except DeliveryError as exc:
            error=exc.code;status=exc.status
            state='uncertain' if exc.uncertain else 'retry' if exc.retryable and attempts<3 else 'failed'
            if state=='retry':retry=at+timedelta(minutes=2**attempts)
        except Exception:state='uncertain';error='delivery_unknown'
        with session_factory() as db:
            db.execute(update(Reminder).where(Reminder.id==rid,Reminder.state=='sending').values(state=state,error=error,http_status=status,retry_at=retry,sent_at=now() if state=='sent' else None,lease_until=None));db.commit()
