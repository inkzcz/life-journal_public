"""Actual saved configuration/scheduler; fake outbound transport only."""
import json
from datetime import datetime,timedelta,timezone
from sqlalchemy import select,update
from test_content import client
from test_api import SessionLocal,csrf,reset_limiter
from test_anniversary_calendar import setup_reminders,leave_synthetic_notifications_disabled
from app.calendar.service import config,KEY
from app.services.blog import save_config
from app.calendar.scheduler import tick
from app.calendar.models import Reminder
from app.calendar.transport import DeliveryError


def test_preview_never_resolves_or_sends_and_saved_test_uses_saved_post(client,monkeypatch):
    from app.calendar import router,transport
    monkeypatch.setattr(transport.socket,'getaddrinfo',lambda *a,**k:(_ for _ in ()).throw(AssertionError('No network for preview')))
    before=client.get('/api/admin/calendar/notification').json()
    candidate={**before,'enabled':False,'method':'POST','headers':[{'name':'Authorization','value':'Bearer synthetic-private-value'}],
        'body_format':'json','body_template':'{"appToken":"synthetic-private-value","content":"{content}"}',
        'url_template':'https://example.invalid/private-synthetic-path?key=synthetic-private-value'}
    assert client.post('/api/admin/calendar/notification/preview',json=candidate).status_code==403
    preview=client.post('/api/admin/calendar/notification/preview',headers=csrf(client),json=candidate)
    assert preview.status_code==200,preview.text
    assert preview.json()['external_request_sent'] is False and 'synthetic-private-value' not in preview.text
    assert client.get('/api/admin/calendar/notification').json()==before
    saved=client.put('/api/admin/calendar/notification',headers=csrf(client),json=candidate)
    assert saved.status_code==200,saved.text
    observed=[]
    def fake(c,variables,**kwargs):observed.append(c);return 204
    monkeypatch.setattr(router,'deliver',fake)
    result=client.post('/api/admin/calendar/notification/test',headers=csrf(client))
    assert result.status_code==200 and result.json()['http_status']==204
    assert observed[0]['method']=='POST' and observed[0]['body_template']==candidate['body_template']
    assert 'synthetic-private-value' not in result.text


def test_post_unknown_outcome_is_durable_and_never_automatically_resent(client):
    event=setup_reminders(client)
    with SessionLocal() as db:
        db.execute(update(Reminder).where(Reminder.state.in_(['queued','retry'])).values(state='cancelled',error='synthetic-test-isolation'))
        rev,c=config(db);save_config(db,KEY,{**c,'method':'POST','body_format':'json','body_template':'{"content":"{content}"}'},rev);db.commit()
    calls=[]
    def uncertain(method,url,headers,body):
        calls.append(method);assert method=='POST' and 'content' in json.loads(body)
        raise DeliveryError('delivery_unknown',uncertain=True)
    at=datetime(2026,11,20,2,tzinfo=timezone.utc)
    tick(SessionLocal,at,request_sender=uncertain)
    tick(SessionLocal,at+timedelta(minutes=10),request_sender=uncertain)
    assert calls==['POST']
    with SessionLocal() as db:
        row=db.scalar(select(Reminder).where(Reminder.anniversary_id==event['id'],Reminder.offset==0))
        assert row.state=='uncertain' and row.attempts==1 and row.channel.startswith('post:')
