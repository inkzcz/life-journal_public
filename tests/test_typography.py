from test_content import client
from test_api import csrf,reset_limiter,SessionLocal
from app.blog_models import SiteConfig
from sqlalchemy import select

def test_typography_persists_without_touching_appearance_and_conflicts(client):
    appearance=client.get('/api/admin/blog/appearance').json()
    before=client.get('/api/blog/typography').json()
    assert before['reader_line'] is None
    data={'editor_line':1.25,'editor_gap':4,'reader_line':1.75,'reader_gap':12,'expected_revision':before['revision']}
    r=client.put('/api/admin/blog/typography',headers=csrf(client),json=data)
    assert r.status_code==200,r.text
    assert client.get('/api/blog/typography').json()['reader_gap']==12
    assert client.put('/api/admin/blog/typography',headers=csrf(client),json=data).status_code==409
    assert client.get('/api/admin/blog/appearance').json()==appearance
    with SessionLocal() as db:assert db.scalar(select(SiteConfig).where(SiteConfig.key=='typography')).value['editor_line']==1.25

def test_typography_rejects_css_and_requires_csrf(client):
    current=client.get('/api/blog/typography').json();data={k:v for k,v in current.items() if k!='revision'}|{'expected_revision':current['revision']}
    assert client.put('/api/admin/blog/typography',json=data).status_code==403
    for bad in ['url(javascript:x)',True,9]:
        assert client.put('/api/admin/blog/typography',headers=csrf(client),json={**data,'editor_line':bad}).status_code==422

def test_reader_can_read_but_cannot_write_typography(client):
    import secrets,uuid
    from datetime import datetime,timedelta,timezone
    from fastapi.testclient import TestClient
    from test_api import app
    from app.models import User,Session
    from app.security import digest
    token=secrets.token_urlsafe(32)
    with SessionLocal() as db:
        user=User(username='reader-'+uuid.uuid4().hex,password_hash='synthetic-unusable-hash');db.add(user);db.flush()
        db.add(Session(user_id=user.id,token_hash=digest(token),expires_at=datetime.now(timezone.utc)+timedelta(hours=1)));db.commit()
    with TestClient(app,base_url='https://testserver') as reader:
        assert reader.get('/api/blog/typography').status_code==401
        reader.cookies.set('life_session',token)
        state=reader.get('/api/blog/typography');assert state.status_code==200
        values=state.json();revision=values.pop('revision')
        assert reader.put('/api/admin/blog/typography',headers=csrf(reader),json={**values,'expected_revision':revision}).status_code==403

def test_reader_mode_defaults_validation_and_legacy_client_preservation(client):
    before=client.get('/api/blog/typography').json()
    assert before['reader_mode']=='full'
    for mode in ['plain','cards','full']:
        current=client.get('/api/blog/typography').json()
        revision=current.pop('revision')
        response=client.put('/api/admin/blog/typography',headers=csrf(client),json={**current,'reader_mode':mode,'expected_revision':revision})
        assert response.status_code==200,response.text
        assert response.json()['reader_mode']==mode
    current=response.json();revision=current.pop('revision')
    response=client.put('/api/admin/blog/typography',headers=csrf(client),json={**current,'reader_mode':'cards','expected_revision':revision})
    legacy=response.json();revision=legacy.pop('revision');legacy.pop('reader_mode')
    response=client.put('/api/admin/blog/typography',headers=csrf(client),json={**legacy,'expected_revision':revision})
    assert response.json()['reader_mode']=='cards'
    assert client.put('/api/admin/blog/typography',headers=csrf(client),json={**legacy,'reader_mode':'unsafe','expected_revision':response.json()['revision']}).status_code==422
