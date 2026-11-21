import uuid
from datetime import date
from test_content import client,make_type,record_payload,write,update_payload
from test_api import reset_limiter,csrf
from app.services.itinerary import extract
A='/api/admin/content/records/'
def test_offline_parser_dates_relative_leap_and_code():
    body='2026-12-31\n09:30 乘高铁出发\n第二天 12:00 品尝午餐\n1月2日 游览公园\n```\n2027-01-03 隐藏代码\n```\n2027-02-30 错误日期'
    r=extract(body,date(2026,12,31),date(2027,1,4));assert [(x['day'],x['kind']) for x in r['items']]==[('2026-12-31','transport'),('2027-01-01','food'),('2027-01-02','sight')]
    assert len(r['warnings'])==1
    assert not extract('第一天 无锚点')['items']
    assert extract('2028年2月29日 08:00 早晨散步')['items'][0]['day']=='2028-02-29'

def test_saved_preview_append_preserves_manual_and_stale_conflict(client):
    t=make_type(client);manual={'id':str(uuid.uuid4()),'day':'2026-10-20','title':'手工活动','media_ids':[]}
    body='2026-10-20\n12:30 品尝午餐'
    r=write(client,'/records',{**record_payload(t),'status':'draft','body':body,'life':{'start_date':'2026-10-20','end_date':'2026-10-21','activities':[manual]}}).json()
    payload={'expected_revision':r['revision'],'body':body};preview=client.post(A+r['id']+'/itinerary-preview',headers=csrf(client),json=payload);assert preview.status_code==200,preview.text;p=preview.json();assert len(p['items'])==1
    data={**payload,'body_hash':p['body_hash'],'selected':[p['items'][0]['source_key']]}
    confirmed=client.post(A+r['id']+'/itinerary-confirm',headers=csrf(client),json=data);assert confirmed.status_code==200,confirmed.text
    assert client.get(A+r['id']).json()['revision']==1  # preview/confirm never saves or publishes
    item=confirmed.json()['items'][0]|{'dish':'合成面食','price':'28.50','currency':'CNY','rating':4,'experience':'温暖的一餐'}
    updated=write(client,'/records/'+r['id'],update_payload(r,life={**r['life'],'activities':r['life']['activities']+[item]}),'put');assert updated.status_code==200,updated.text;u=updated.json()
    assert u['life']['activities'][0]['id']==manual['id'];assert u['life']['activities'][1]['price']=='28.50'
    assert client.post(A+r['id']+'/itinerary-confirm',headers=csrf(client),json=data).status_code==409
    p2=client.post(A+r['id']+'/itinerary-preview',headers=csrf(client),json={'expected_revision':u['revision'],'body':body}).json();assert not p2['items']
    invalid={**item,'rating':6};assert write(client,'/records/'+r['id'],update_payload(u,life={**u['life'],'activities':[invalid]}),'put').status_code==422
