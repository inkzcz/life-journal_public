"""Appearance JSONB is additive: old clients, records and security stay compatible."""
import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from test_blog import config_put,put,A,B,reader_client
from test_content import client,make_type
from test_archive import create_record
from test_api import app,login,csrf,engine,reset_limiter
from app.blog_schemas import AppearanceEdit
from pydantic import ValidationError

KEYS=['page_background','card_background','body_text','heading_text','muted_text','nav_background','nav_text','link','primary_background','primary_text','secondary_background','secondary_text','tag_background','tag_text','border','accent']

def test_all_colors_modes_themes_persist_and_old_client_preserves(client):
    t=make_type(client);record=create_record(client,t)
    before=client.get('/api/admin/content/records/'+record['id']).json()
    layout=client.get(A+'/layout').json()
    colors={theme:{mode:{key:'#12aBcD' for key in KEYS} for mode in ['light','dark']} for theme in ['modern','editorial','soft','glass','celadon']}
    result=config_put(client,'appearance',theme='modern',mode='system',colors=colors);assert result.status_code==200,result.text
    assert client.get(B+'/site').json()['appearance']['colors']==colors
    old={'theme':'glass','mode':'dark','expected_revision':result.json()['revision']}
    changed=put(client,'/appearance',old);assert changed.status_code==200
    assert changed.json()['colors']==colors
    assert put(client,'/appearance',old).status_code==409
    assert client.get('/api/admin/content/records/'+record['id']).json()==before
    assert client.get(A+'/layout').json()==layout
    # Explicit sparse replacement and clearing never deletes any record data.
    one=copy.deepcopy(colors);del one['glass']
    assert config_put(client,'appearance',colors=one).json()['colors']==one
    assert 'colors' not in config_put(client,'appearance',colors={}).json()
    assert client.get(B+'/records/'+record['id']).status_code==200
    assert 'colors' not in config_put(client,'appearance',colors={'modern':{'light':{}}}).json()

@pytest.mark.parametrize('value',['red','#fff','#12345678','#12345g',' #123456','#123456\n','var(--ink)','url(https://evil.invalid)','</style><script>evil()</script>',12,None,True,{}])
def test_invalid_color_cannot_save(client,value):
    before=client.get(A+'/appearance').json()
    assert config_put(client,'appearance',colors={'modern':{'light':{'body_text':value}}}).status_code==422
    assert client.get(A+'/appearance').json()==before

@pytest.mark.parametrize('colors',[{'evil':{}},{'modern':{'system':{}}},{'modern':{'light':{'position':'#112233'}}},{'modern':None},None,[]])
def test_palette_keys_are_a_finite_whitelist(colors):
    with pytest.raises(ValidationError):AppearanceEdit(theme='modern',mode='system',expected_revision=0,colors=colors)

def test_colors_permissions_switch_csrf(client):
    with reader_client(client.app) as reader:
        assert reader.get(B+'/site').status_code==200
        assert reader.get(A+'/appearance').status_code==403
        assert reader.put(A+'/appearance',headers=csrf(reader),json={'expected_revision':0,'colors':{}}).status_code==403
    with TestClient(client.app,base_url='https://testserver') as anon:
        assert anon.get(B+'/site').status_code==401
    assert client.put(A+'/appearance',json={'expected_revision':0,'colors':{}}).status_code==403
    with TestClient(app,base_url='https://testserver') as off:
        login(off);assert off.get(A+'/appearance').status_code==200
        assert off.get('/api/journals').status_code==200


def test_color_cas_concurrent_updates(client):
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL concurrency')
    current=client.get(A+'/appearance').json()
    def save(color):
        with TestClient(client.app,base_url='https://testserver') as other:
            login(other)
            return put(other,'/appearance',{'theme':'modern','mode':'light','colors':{'modern':{'light':{'link':color}}},'expected_revision':current['revision']}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(save,['#123456','#654321']))==[200,409]
    assert client.get(A+'/appearance').json()['colors']['modern']['light']['link'] in {'#123456','#654321'}


def test_modern_soft_defaults_and_legacy_identity_without_rewriting(client):
    from types import SimpleNamespace
    from app.blog_schemas import Appearance
    from app.services.blog import config_data
    class ConfigDB:
        def __init__(self,row):self.row=row
        def scalar(self,query):return self.row
    assert Appearance().theme=='celadon'
    # Row-less legacy sites cannot be identified as new installations. Preserve fallback.
    assert config_data(ConfigDB(None),'appearance')=={'theme':'modern','mode':'system','revision':0}
    original={'theme':'soft','mode':'system','colors':{'soft':{'light':{k:'#123456' for k in KEYS}}}}
    snapshot=copy.deepcopy(original)
    assert config_data(ConfigDB(SimpleNamespace(value=original,revision=8)),'appearance')=={**original,'revision':8}
    assert original==snapshot
    saved=config_put(client,'appearance',**original);assert saved.status_code==200,saved.text
    celadon=config_put(client,'appearance',theme='celadon');assert celadon.status_code==200
    assert celadon.json()['colors']==original['colors']
    back=config_put(client,'appearance',theme='soft')
    assert back.json()['colors']==original['colors']
    assert client.get(B+'/site').json()['appearance']['theme']=='soft'


def test_independent_style_palette_bank_reset_and_old_client_compatibility(client):
    legacy={'soft':{'light':{'accent':'#65479a'}},'glass':{'dark':{'body_text':'#ffffff'}}}
    saved=config_put(client,'appearance',theme='soft',mode='system',colors=legacy)
    assert saved.status_code==200
    bank={}
    for style in ['modern-flat','editorial','modern-soft','glass']:
        for palette in ['celadon','lilac']:
            bank.setdefault(style,{})[palette]={'light':{k:'#123456' for k in KEYS},'dark':{k:'#abcdef' for k in KEYS}}
            result=config_put(client,'appearance',style=style,palette=palette,combination_colors=bank)
            assert result.status_code==200,result.text
            assert result.json()['style']==style and result.json()['palette']==palette
            assert result.json()['colors']==legacy
    before=client.get(A+'/appearance').json()
    partial=put(client,'/appearance',{'style':'modern-flat','expected_revision':before['revision']})
    assert partial.json()['theme']=='soft' and partial.json()['palette']=='lilac'
    before=partial.json()
    old=put(client,'/appearance',{'theme':'soft','mode':'dark','expected_revision':before['revision']})
    assert old.status_code==200 and old.json()['style']=='modern-flat' and old.json()['palette']=='lilac'
    assert old.json()['combination_colors']==bank and old.json()['colors']==legacy
    reset=copy.deepcopy(bank);reset['glass']['lilac']={'light':{},'dark':{}}
    current=config_put(client,'appearance',combination_colors=reset)
    assert current.json()['combination_colors']['glass']['lilac']=={'light':{},'dark':{}}
    assert current.json()['colors']==legacy
    # A genuine legacy theme switch returns to compatibility colors but archives bank.
    switched=put(client,'/appearance',{'theme':'editorial','mode':'light','expected_revision':current.json()['revision']})
    assert 'style' not in switched.json() and 'palette' not in switched.json()
    assert switched.json()['combination_colors']==reset and switched.json()['colors']==legacy
    assert put(client,'/appearance',{'theme':'editorial','style':'execute-css','expected_revision':switched.json()['revision']}).status_code==422
    assert config_put(client,'appearance',style='glass',palette='lilac',combination_colors={'glass':{'lilac':{'light':{'accent':'url(evil)'}}}}).status_code==422
