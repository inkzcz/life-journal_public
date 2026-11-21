"""Structured food and media compile through the original parser and ownership rules."""
import uuid,json
from datetime import date
import pytest
from test_api import reset_limiter,engine
from app.exchange.schemas import Exchange
from app.exchange.assemble import compile_record
from app.services.markdown_marks import parse
from app.services.body_media import blocks
from fastapi import HTTPException


def sample():
    return Exchange.model_validate({'format':'life-journal.exchange','version':1,'records':[{'key':'trip','type_slug':'custom','title':'两天两餐厅','display_date':'2026-11-05','body':'正文前\n\n{{media:one}}\n\n正文后','travel':{'start_date':'2026-10-01','end_date':'2026-10-02'},'foods':[{'place_key':'a','day':'2026-10-01','review':'甲餐厅评价','media_keys':['one']},{'place_key':'b','day':'2026-10-02','review':'乙餐厅评价','media_keys':['two']}]}],
        'media':[{'key':'one','existing_id':str(uuid.uuid4())},{'key':'two','existing_id':str(uuid.uuid4())}],
        'places':[{'key':'a','kind':'f','name':'甲餐厅','city':'成都'},{'key':'b','kind':'f','name':'乙餐厅','city':'成都'}]})

def test_compilation_preserves_dates_and_owns_photos_per_restaurant():
    value=sample();mid={m.key:str(m.existing_id) for m in value.media};pid={p.key:str(uuid.uuid4()) for p in value.places}
    result=compile_record(value.records[0],value,mid,pid,str(uuid.uuid4()))
    document=parse(result['body']);foods=document.food(date(2026,10,1),date(2026,10,2),bounded=True)
    assert [(f['mark']['name'],f['day']) for f in foods]==[('甲餐厅',date(2026,10,1)),('乙餐厅',date(2026,10,2))]
    assert [m['id'] for m in blocks(result['body'],2)]==[mid['one'],mid['one'],mid['two']]
    assert '正文前' in result['body'] and '正文后' in result['body'] and '{{media:' not in result['body']
    assert len(result['markdown_activity_ids'])==2
    assert [a['media_ids'] for a in result['life']['activities']]==[[mid['one']],[mid['two']]]

def test_missing_food_date_never_inherits_previous_day_silently():
    value=sample();value.records[0].foods[1].day=None
    with pytest.raises(HTTPException) as caught:compile_record(value.records[0],value,{m.key:str(m.existing_id) for m in value.media},{p.key:str(uuid.uuid4()) for p in value.places},str(uuid.uuid4()))
    assert '不会猜测' in caught.value.detail


def test_same_restaurant_same_day_meals_remain_distinct_without_clock_times():
    value=sample();value.records[0].foods[1].place_key='a';value.records[0].foods[1].day=value.records[0].foods[0].day
    mids={m.key:str(m.existing_id) for m in value.media};pids={p.key:str(uuid.uuid4()) for p in value.places};id=str(uuid.uuid4())
    one=compile_record(value.records[0],value,mids,pids,id);two=compile_record(value.records[0],value,mids,pids,id)
    assert len(one['life']['activities'])==2
    assert one['life']==two['life'] and len(set(one['markdown_activity_ids']))==2
    assert one['life']['activities'][0]['media_ids']==[mids['one']]
    assert one['life']['activities'][1]['media_ids']==[mids['two']]
    assert len(parse(one['body']).food(date(2026,10,1),date(2026,10,2),bounded=True))==2
