"""Current mode is independent of the legacy type; reads never rewrite data."""
import pytest
import uuid
from test_content import client, write, record_payload
from test_api import SessionLocal
from app.content_models import ContentRecord
from app.services.blog import summary

@pytest.mark.parametrize('type_name',['日常记录','旅行记录'])
@pytest.mark.parametrize('enabled',[False,True])
def test_reader_summary_uses_explicit_mode_without_changing_identity(client,type_name,enabled):
    t=write(client,'/types',{'slug':'synthetic-'+uuid.uuid4().hex[:12],'name':type_name,'fields':[]}).json()
    response=write(client,'/records',record_payload(t,article={'travel_enabled':enabled}))
    assert response.status_code==200,response.text
    saved=response.json()
    with SessionLocal() as db:
        record=db.get(ContentRecord,saved['id'])
        before=(record.id,record.type_id,record.body,dict(record.values))
        value=summary(db,record)
        assert value['type_name']==type_name
        assert value['travel_enabled'] is enabled
        assert value['record_mode_name']==('旅行记录' if enabled else '日常记录')
        assert (record.id,record.type_id,record.body,dict(record.values))==before

    for mode in ('daily','travel'):
        result=client.get('/api/blog/archive',params={'type':t['id'],'record_mode':mode}).json()
        assert result['total']==int(enabled==(mode=='travel'))
    archive=client.get('/api/experiences/trips').json()
    assert (saved['id'] in {r['id'] for r in archive['items']}) is enabled
    detail=client.get('/api/blog/records/'+saved['id']).json()
    assert detail['article']['travel_enabled'] is enabled


def test_legacy_fallback_is_used_only_until_explicit_false_is_saved(client):
    from app.experience_models import ArticleOptions
    from app.life_models import TripPlan
    from datetime import date
    t=write(client,'/types',{'slug':'synthetic-'+uuid.uuid4().hex[:12],'name':'历史类型','fields':[]}).json()
    saved=write(client,'/records',record_payload(t)).json()
    with SessionLocal() as db:
        row=db.get(ArticleOptions,saved['id'])
        if row:db.delete(row)
        plan=db.get(TripPlan,saved['id'])
        if plan:plan.start_date=date(2026,10,18)
        else:db.add(TripPlan(record_id=saved['id'],start_date=date(2026,10,18)))
        db.commit()
    assert client.get('/api/blog/records/'+saved['id']).json()['travel_enabled'] is True
    with SessionLocal() as db:
        db.add(ArticleOptions(record_id=saved['id'],travel_enabled=False));db.commit()
    detail=client.get('/api/blog/records/'+saved['id']).json()
    assert detail['travel_enabled'] is False and detail['article']['travel_enabled'] is False
    with SessionLocal() as db:assert db.get(TripPlan,saved['id']).start_date==date(2026,10,18)
