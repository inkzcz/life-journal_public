import uuid
from datetime import date,datetime,timezone,timedelta
from urllib.parse import parse_qs,urlsplit
import pytest
from sqlalchemy import select,delete
from test_content import client,make_type,record_payload,write
from test_api import SessionLocal,csrf,reset_limiter
from app.calendar.dates import DateRule,occurrences,years_at
from app.calendar.models import Anniversary,Reminder
from app.calendar.scheduler import tick
from app.calendar.transport import template,render,resolve,DeliveryError
from app.services.blog import save_config
from app.calendar.service import KEY,config

@pytest.fixture(autouse=True)
def leave_synthetic_notifications_disabled():
    yield
    from app.blog_models import SiteConfig
    with SessionLocal() as db:
        c=db.scalar(select(SiteConfig).where(SiteConfig.key==KEY))
        if c and c.value.get('enabled'):
            c.value={**c.value,'enabled':False};c.revision+=1;db.commit()

def test_solar_leap_monthly_weekly_and_invalid_rules():
    r=DateRule(year=2024,month=2,day=29)
    assert occurrences(r,date(2025,1,1),date(2025,12,31))==[]
    assert occurrences(r.model_copy(update={'missing':'last_day'}),date(2025,1,1),date(2025,12,31))==[date(2025,2,28)]
    assert occurrences(r.model_copy(update={'missing':'march_1'}),date(2025,1,1),date(2025,12,31))==[date(2025,3,1)]
    m=DateRule(year=2026,month=3,day=31,repeat='monthly',missing='last_day')
    assert occurrences(m,date(2026,1,1),date(2026,5,31))==[date(2026,3,31),date(2026,4,30),date(2026,5,31)]
    assert len(occurrences(DateRule(year=2026,month=1,day=1,repeat='weekly'),date(2026,1,1),date(2026,1,31)))==5
    with pytest.raises(ValueError):DateRule(year=2025,month=2,day=29)

def test_real_lunar_conversion_and_explicit_missing_leap_month():
    lunar=DateRule(calendar='lunar',year=2023,month=1,day=1)
    assert occurrences(lunar,date(2024,1,1),date(2024,12,31))==[date(2024,2,10)]
    assert occurrences(lunar,date(2025,1,1),date(2025,12,31))==[date(2025,1,29)]
    assert years_at(lunar,date(2025,1,29))==2
    leap=DateRule(calendar='lunar',year=2023,month=2,day=1,leap_month=True)
    assert occurrences(leap,date(2024,1,1),date(2024,12,31))==[]
    assert occurrences(leap.model_copy(update={'lunar_leap':'regular'}),date(2024,1,1),date(2024,12,31))==[date(2024,3,10)]
    with pytest.raises(ValueError):DateRule(calendar='lunar',year=2100,month=1,day=1)

def test_query_values_are_encoded_once_without_parameter_injection():
    url=render('https://notify.example.invalid/send?token=synthetic%2Bvalue&title={title}&content={content}',{'title':'中文 & = ? + %','content':'测试\n第二行'})
    parsed=parse_qs(urlsplit(url).query)
    assert parsed=={'token':['synthetic+value'],'title':['中文 & = ? + %'],'content':['测试\n第二行']}
    for value in ('file:///etc/passwd','http://user:synthetic@notify.invalid','https://{name}.invalid/send','https://notify.invalid/{title}','https://notify.invalid/send?title={unknown}','https://notify.invalid/?{name}=x'):
        with pytest.raises(ValueError):template(value)

@pytest.mark.parametrize('ip',['127.0.0.1','169.254.169.254','10.0.0.1','::1','::ffff:127.0.0.1','100.100.100.200','224.0.0.1'])
def test_ssrf_blocked_before_send(monkeypatch,ip):
    monkeypatch.setattr('socket.getaddrinfo',lambda *a,**k:[(2,1,6,'',(ip,443))])
    with pytest.raises(DeliveryError):resolve(urlsplit('https://notify.example.invalid/send'))

def test_explicit_internal_origin_requires_all_dns_addresses_pinned(monkeypatch):
    monkeypatch.setenv('LJ_NOTIFY_INTERNAL_ORIGIN_IPS','{"http://notify.internal:8080":["10.0.0.5"]}')
    monkeypatch.setattr('socket.getaddrinfo',lambda *a,**k:[(2,1,6,'',('10.0.0.5',8080))])
    assert resolve(urlsplit('http://notify.internal:8080/send'))=='10.0.0.5'
    monkeypatch.setattr('socket.getaddrinfo',lambda *a,**k:[(2,1,6,'',('10.0.0.6',8080))])
    with pytest.raises(DeliveryError):resolve(urlsplit('http://notify.internal:8080/send'))

def event_data(**changes):return {'name':'合成生日','kind':'birthday','rule':{'year':2000,'month':11,'day':20,'repeat':'yearly'},'reminders':{'enabled':True,'on_day':True,'offsets':[7,3,1]},**changes}

def test_dynamic_memories_include_backdated_multiday_articles_and_separate_manual(client):
    res=client.post('/api/admin/calendar/events',headers=csrf(client),json=event_data());assert res.status_code==200,res.text;e=res.json()
    t=make_type(client);a=write(client,'/records',{**record_payload(t),'display_date':'2020-11-20','title':'补写旧文'}).json()
    b=write(client,'/records',{**record_payload(t),'display_date':'2021-11-19','article':{'end_date':'2021-11-21','travel_enabled':False}}).json()
    draft=write(client,'/records',{**record_payload(t),'display_date':'2022-11-20','status':'draft'}).json()
    detail=client.get('/api/calendar/'+e['id']);assert detail.status_code==200,detail.text
    ids={x['id'] for x in detail.json()['day_memories']};assert a['id'] in ids and b['id'] in ids and draft['id'] not in ids
    update=event_data(memories=[a['id']],expected_revision=e['revision'])
    assert client.put('/api/admin/calendar/events/'+e['id'],headers=csrf(client),json=update).status_code==200
    d=client.get('/api/calendar/'+e['id']).json();assert [x['id'] for x in d['dedicated_memories']]==[a['id']];assert a['id'] not in [x['id'] for x in d['day_memories']]

def setup_reminders(client):
    with SessionLocal() as db:
        # Isolate synthetic events from earlier examples, preserve all log rows.
        for e in db.scalars(select(Anniversary)):e.active=False
        rev,_=config(db);save_config(db,KEY,{'enabled':True,'url_template':'https://notify.example.invalid/send?title={title}&content={content}','timezone':'Asia/Shanghai','time':'09:00'},rev);db.commit()
    e=client.post('/api/admin/calendar/events',headers=csrf(client),json=event_data()).json()
    return e

def test_four_offsets_independent_persistent_and_no_duplicate_reschedule(client):
    e=setup_reminders(client);sent=[]
    for day in (13,17,19,20):
        at=datetime(2026,11,day,2,tzinfo=timezone.utc)
        for _ in range(2):tick(SessionLocal,at,send=lambda url:sent.append(url) or 200)
    assert len(sent)==4
    with SessionLocal() as db:
        rows=list(db.scalars(select(Reminder).where(Reminder.anniversary_id==e['id'])))
        assert {r.offset for r in rows}=={0,1,3,7} and all(r.state=='sent' for r in rows)
        assert all(r.attempts==1 for r in rows)

def test_retry_backoff_and_unknown_timeout_is_not_automatically_resent(client):
    e=setup_reminders(client);at=datetime(2026,11,13,2,tzinfo=timezone.utc);calls=[]
    def fail(url):calls.append(url);raise DeliveryError('http_error',retryable=True,status=500)
    tick(SessionLocal,at,send=fail);tick(SessionLocal,at,send=fail);assert len(calls)==1
    tick(SessionLocal,at+timedelta(minutes=8),send=lambda _:200)
    with SessionLocal() as db:assert db.scalar(select(Reminder).where(Reminder.anniversary_id==e['id'])).state=='sent'
    def unknown(url):raise DeliveryError('delivery_unknown',uncertain=True)
    tick(SessionLocal,datetime(2026,11,17,2,tzinfo=timezone.utc),send=unknown)
    tick(SessionLocal,datetime(2026,11,17,3,tzinfo=timezone.utc),send=lambda _:pytest.fail('uncertain node auto resent'))
    with SessionLocal() as db:assert db.scalar(select(Reminder).where(Reminder.anniversary_id==e['id'],Reminder.offset==3)).state=='uncertain'
    logs=client.get('/api/admin/calendar/logs');assert logs.status_code==200 and 'notify.example' not in logs.text


def test_concurrent_workers_claim_one_node_and_interrupted_claim_is_uncertain(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock
    e=setup_reminders(client);sent=[];lock=Lock();at=datetime(2026,11,13,2,tzinfo=timezone.utc)
    def send(url):
        with lock:sent.append(url)
        return 200
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:tick(SessionLocal,at,send=send),range(2)))
    assert len(sent)==1
    with SessionLocal() as db:
        row=db.scalar(select(Reminder).where(Reminder.anniversary_id==e['id']));row.state='sending';row.lease_until=at-timedelta(seconds=1);db.commit()
    tick(SessionLocal,at,send=lambda _:pytest.fail('interrupted claim automatically resent'))
    with SessionLocal() as db:assert db.scalar(select(Reminder).where(Reminder.anniversary_id==e['id'])).state=='uncertain'


def test_get_transport_real_local_fixture_and_redirect_refusal(monkeypatch):
    import threading
    from http.server import HTTPServer,BaseHTTPRequestHandler
    from app.calendar.transport import get
    seen=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            self.send_response(302 if self.path.startswith('/redirect') else 200)
            if self.path.startswith('/redirect'):self.send_header('Location','http://169.254.169.254/never')
            self.end_headers();self.wfile.write(b'synthetic-ok')
        def log_message(self,*a):pass
    server=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();origin='http://127.0.0.1:'+str(server.server_port)
    monkeypatch.setenv('LJ_NOTIFY_INTERNAL_ORIGIN_IPS','{"'+origin+'":["127.0.0.1"]}')
    try:
        assert get(render(origin+'/send?name={name}',{'name':'中文 & +'}))==200
        assert parse_qs(urlsplit(seen[0]).query)=={'name':['中文 & +']}
        with pytest.raises(DeliveryError,match='redirect_refused'):get(origin+'/redirect')
        assert len(seen)==2
    finally:server.shutdown();thread.join(timeout=3);server.server_close()


def test_calendar_and_notification_configuration_permissions(client):
    from test_blog import reader_client
    c=reader_client(client.app)
    assert c.get('/api/calendar').status_code==200
    for path in ('notification','events','logs'):assert c.get('/api/admin/calendar/'+path).status_code==403
    assert 'url_template' not in c.get('/api/calendar').text
    invalid=client.put('/api/admin/calendar/notification',headers=csrf(client),json={'enabled':False,'timezone':'Invalid/Synthetic','time':'09:00','expected_revision':0});assert invalid.status_code==422


def test_real_get_four_independent_nodes_through_persisted_scheduler(client,monkeypatch):
    import threading
    from http.server import HTTPServer,BaseHTTPRequestHandler
    from app.calendar.transport import get
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append(parse_qs(urlsplit(self.path).query));self.send_response(200);self.end_headers();self.wfile.write(b'ok')
        def log_message(self,*a):pass
    server=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();origin='http://127.0.0.1:'+str(server.server_port)
    monkeypatch.setenv('LJ_NOTIFY_INTERNAL_ORIGIN_IPS','{"'+origin+'":["127.0.0.1"]}')
    e=setup_reminders(client)
    with SessionLocal() as db:
        rev,c=config(db);save_config(db,KEY,c|{'url_template':origin+'/send?title={title}&name={name}&days={days_left}'},rev);db.commit()
    try:
        for day in (13,17,19,20):
            at=datetime(2026,11,day,2,tzinfo=timezone.utc)
            tick(SessionLocal,at,send=get);tick(SessionLocal,at,send=get)
        assert len(received)==4 and {v['days'][0] for v in received}=={'0','1','3','7'}
        assert all(v['name']==['合成生日'] for v in received)
        log=[x for x in client.get('/api/admin/calendar/logs').json() if x['anniversary_id']==e['id']]
        assert len(log)==4 and all(x['state']=='sent' and x['http_status']==200 and x['attempted_at'] and x['sent_at'] for x in log)
    finally:server.shutdown();thread.join(timeout=3);server.server_close()


def test_unchanged_notification_save_keeps_channel_identity(client):
    before=client.get('/api/admin/calendar/notification').json()
    assert before['enabled'] is False
    result=client.put('/api/admin/calendar/notification',headers=csrf(client),json=before)
    assert result.status_code==200,result.text
    assert result.json()['unchanged'] and result.json()['revision']==before['expected_revision']
    assert client.get('/api/admin/calendar/notification').json()==before


def test_dynamic_memories_paginate_without_dropping_history(client):
    e=client.post('/api/admin/calendar/events',headers=csrf(client),json=event_data(name='合成分页纪念日',rule={'year':2000,'month':6,'day':15,'repeat':'yearly'})).json()
    t=make_type(client)
    ids=set()
    for n in range(26):ids.add(write(client,'/records',{**record_payload(t),'title':'分页回忆'+str(n),'display_date':'2020-06-15'}).json()['id'])
    first=client.get('/api/calendar/'+e['id']).json();second=client.get('/api/calendar/'+e['id'],params={'memory_page':2}).json()
    assert first['day_memory_total']==26 and len(first['day_memories'])==24 and len(second['day_memories'])==2
    assert {x['id'] for x in first['day_memories']+second['day_memories']}==ids


def test_home_calendar_uses_existing_layout_limits_order_visibility_and_reader_permissions(client,monkeypatch):
    from test_blog import config_put,module,reader_client
    monkeypatch.setattr('app.calendar.service.today',lambda db:date(2026,11,13))
    with SessionLocal() as db:
        for e in db.scalars(select(Anniversary)):e.active=False
        db.commit()
    for name,day in [('今天的合成事件',13),('明天的合成事件',14)]:
        r=client.post('/api/admin/calendar/events',headers=csrf(client),json=event_data(name=name,rule={'year':2000,'month':11,'day':day}));assert r.status_code==200,r.text
    m=module('anniversary_calendar',title='重要日子',count=1,horizon=0,show_countdown=False,show_years=False)
    assert config_put(client,'layout',modules=[m,module('text',text='保留其他模块')]).status_code==200
    with reader_client(client.app) as reader:
        data=reader.get('/api/blog/home').json()['modules'];assert [x['kind'] for x in data]==['anniversary_calendar','text']
        assert len(data[0]['events'])==1 and data[0]['events'][0]['days_left']==0
        assert data[0]['events'][0]['name']=='今天的合成事件' and data[0]['events'][0]['years']==26
        assert not data[0]['show_countdown'] and not data[0]['show_years']
        assert reader.get('/api/admin/calendar/notification').status_code==403
    assert config_put(client,'layout',modules=[{**m,'enabled':False}]).status_code==200
    assert client.get('/api/blog/home').json()['modules']==[]
    assert config_put(client,'layout',modules=[{**m,'horizon':367}]).status_code==422
