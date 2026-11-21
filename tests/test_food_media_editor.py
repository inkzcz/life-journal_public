"""v5.1.4 synthetic food ownership, versioned fields and clean summary guards."""
import json,uuid
import pytest
from test_content import client,make_type,record_payload,write,update_payload
from test_archive import upload
from test_api import csrf,SessionLocal,reset_limiter
from app.services.body_media import safe_excerpt,blocks
from app.content_models import ContentRecord


def media(id):return ':::lj-media-v1\n'+json.dumps({'id':id,'alt':'合成照片','caption':'','width':960,'align':'center'})+'\n:::'

def test_visits_never_inherit_trip_cover_and_explicit_sharing_is_valid(client):
    t=make_type(client);a=upload(client).json();b=upload(client).json();cover=upload(client).json()
    def visit(name,id=None):return '- @f '+name+('\n\n'+'\n'.join('  '+l for l in media(id).splitlines()) if id else '')
    body='@l 合成城市\n\n'+'\n\n'.join([visit('甲餐厅',a['id']),visit('乙餐厅',b['id']),visit('无图餐厅'),visit('主动复用餐厅',a['id'])])
    title='v514-ownership-'+uuid.uuid4().hex
    r=write(client,'/records',{**record_payload(t),'body':body,'body_format':2,'title':title,'connections':{'media':[{'id':cover['id'],'cover':True}]}})
    assert r.status_code==200,r.text
    rows=client.get('/api/food',params={'q':title}).json()['items'];assert len(rows)==4
    actual={x['name']:x['cover_id'] for x in rows}
    assert actual=={'甲餐厅':a['id'],'乙餐厅':b['id'],'无图餐厅':None,'主动复用餐厅':a['id']}
    assert client.get('/api/food/'+rows[0]['id']).json()['cover_id']==rows[0]['cover_id']
    reread=client.get('/api/admin/content/records/'+r.json()['id']).json()
    assert reread['body']==body and reread['connections']['media'][0]['id']==cover['id']

@pytest.mark.parametrize('body,expected',[
    ('前文\n\n'+media('11111111-1111-4111-8111-111111111111')+'\n\n后文','前文 后文'),
    (media('11111111-1111-4111-8111-111111111111')+'\n\n'+media('22222222-2222-4222-8222-222222222222')+'\n\n结尾','结尾'),
    ('# 标题\n\n- **列表** [链接](https://example.invalid)\n\n> 引用\n\n```\n代码\n```','标题 列表 链接 引用 代码'),
    ('前文 :::lj-media-v1\n{"id":"broken","alt":"private"\n后文','前文 后文'),
    (':::lj-media-v1\n{"id":"broken"',''),
    ('没有图片的正文','没有图片的正文'),
])
def test_excerpt_hides_metadata_and_preserves_readable_prose(body,expected):
    assert safe_excerpt(body,2,300)==expected
    assert 'lj-media' not in safe_excerpt(body,1,300)

def test_summary_budget_is_readable_text_and_original_body_is_unchanged(client):
    t=make_type(client);m=upload(client).json();body=media(m['id'])+'\n\n'+'可读正文'*80
    r=write(client,'/records',{**record_payload(t),'body':body,'body_format':2})
    assert r.status_code==200,r.text
    preview=client.get('/api/blog/records/'+r.json()['id']).json()
    from app.services.blog import summary
    with SessionLocal() as db:
        record=db.get(ContentRecord,r.json()['id']);excerpt=summary(db,record)['excerpt'];assert len(excerpt)==220
        assert excerpt=='可读正文'*55 and record.body==body


def test_food_dynamic_fields_are_optional_stable_and_meal_date_is_not_publication(client):
    t=client.post('/api/admin/food/install-template',headers=csrf(client)).json()
    from app.services.content import fields_for
    fields={x['field']['purpose']:x['field'] for x in t['fields']}
    assert len(fields)==5 and all(not x['required'] for x in fields.values())
    values={fields[k]['id']:v for k,v in {'food_shop':'合成店铺','food_date':'2026-10-03','food_city':'合成城市','food_address':'合成街12号','food_review':'味道不错'}.items()}
    data={'type_id':t['type_id'],'schema_version':t['schema_version'],'template':{'id':t['id'],'version':t['version']},'title':'v514-food-'+uuid.uuid4().hex,'body':'餐后故事','display_date':'2026-11-05','status':'published','values':values}
    r=write(client,'/records',data);assert r.status_code==200,r.text;r=r.json()
    item=client.get('/api/food',params={'q':r['title'],'kind':'articles'}).json()['items'][0]
    assert (item['title'],item['shop_name'],item['day'],item['city'],item['address'],item['description'])==(r['title'],'合成店铺','2026-10-03','合成城市','合成街12号','味道不错')
    assert item['travel_source'] is None and r['is_food']
    # Clear optional data: no invented title/shop/date, old record remains readable.
    updated=write(client,'/records/'+r['id'],update_payload(r,values={k:None for k in values}),'put');assert updated.status_code==200,updated.text
    item=client.get('/api/food',params={'q':r['title'],'kind':'articles'}).json()['items'][0]
    assert item['shop_name']=='' and item['day'] is None and item['description']=='餐后故事'


def test_media_layout_validation_is_additive_and_rejects_executable_config():
    data=json.loads(media('11111111-1111-4111-8111-111111111111').splitlines()[1])
    for layout in ['auto','single','grid']:
        body=':::lj-media-v1\n'+json.dumps({**data,'layout':layout})+'\n:::'
        assert blocks(body,2)[0]['layout']==layout
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as rejected:blocks(':::lj-media-v1\n'+json.dumps({**data,'layout':'javascript:bad'})+'\n:::',2)
    assert rejected.value.status_code==422


def test_legacy_food_template_explicit_opt_in_keeps_record_version_until_save(client):
    from app.v5_models import FoodContentType
    t=client.post('/api/admin/templates',headers=csrf(client),json={'slug':'legacy-food-'+uuid.uuid4().hex,'name':'合成历史美食','fields':[],'modules':[{'id':str(uuid.uuid4()),'kind':'body'}]}).json()
    with SessionLocal() as db:db.add(FoodContentType(type_id=t['type_id'],template_id=t['id']));db.commit()
    data={'type_id':t['type_id'],'schema_version':t['schema_version'],'template':{'id':t['id'],'version':t['version']},'title':'历史美食-'+uuid.uuid4().hex,'body':'历史正文保留','display_date':'2026-10-01','status':'published','values':{}}
    r=write(client,'/records',data).json();assert r['fields']==[]
    request={'expected_type_revision':1,'expected_template_revision':1,'confirmation':'新增可选餐厅信息字段'}
    enabled=client.post('/api/admin/food/types/'+t['type_id']+'/fields',headers=csrf(client),json=request)
    assert enabled.status_code==200,enabled.text;enabled=enabled.json();assert enabled['records_changed'] is False
    old=client.get('/api/admin/content/records/'+r['id']).json();assert old['body']==r['body'] and old['revision']==r['revision'] and old['fields']==[]
    assert client.post('/api/admin/food/types/'+t['type_id']+'/fields',headers=csrf(client),json=request).status_code==409
    f=next(x for x in enabled['type']['fields'] if x['purpose']=='food_shop')
    updated=write(client,'/records/'+r['id'],update_payload(r,schema_version=enabled['type']['version'],template={'id':t['id'],'version':enabled['template']['version']},values={f['id']:'手动补充店铺'}),'put')
    assert updated.status_code==200,updated.text
    rows=client.get('/api/food',params={'q':r['title'],'kind':'articles'}).json()['items'];assert rows[0]['shop_name']=='手动补充店铺'
    from app.content_models import RecordRevision
    with SessionLocal() as db:assert db.get(RecordRevision,(r['id'],1)).snapshot['body']==r['body']
    assert client.get('/api/admin/content/records/'+r['id']).json()['body']==r['body']


def test_legacy_malformed_media_is_hidden_on_read_without_changing_body(client):
    t=client.post('/api/admin/food/install-template',headers=csrf(client)).json()
    r=write(client,'/records',{'type_id':t['type_id'],'schema_version':t['schema_version'],'template':{'id':t['id'],'version':t['version']},'title':'legacy-invalid-'+uuid.uuid4().hex,'body':'原正文','display_date':'2026-11-05','status':'published','values':{}}).json()
    broken='前文\n\n:::lj-media-v1\n{"id":"broken","width":"960"}\n:::\n\n后文'
    with SessionLocal() as db:db.get(ContentRecord,r['id']).body=broken;db.commit()
    response=client.get('/api/food',params={'q':r['title'],'kind':'articles'})
    assert response.status_code==200,response.text
    item=response.json()['items'][0];assert item['description']=='前文 后文' and item['cover_id'] is None
    with SessionLocal() as db:assert db.get(ContentRecord,r['id']).body==broken


def test_food_purpose_validation_and_versions_keep_stable_field_ids(client):
    from test_content import field
    bad={'slug':'invalid-purpose-'+uuid.uuid4().hex,'name':'合成无效字段','fields':[field(kind='integer',purpose='food_date')]};assert write(client,'/types',bad).status_code==422
    t=make_type(client,[{**field(purpose='food_shop'),'name':'原店名'}]);fid=t['fields'][0]['id']
    data={k:t[k] for k in ('slug','name','description','active')};data.update(expected_revision=t['revision'],fields=[{**t['fields'][0],'name':'改名后的店铺字段'}])
    changed=write(client,'/types/'+t['id'],data,'put');assert changed.status_code==200,changed.text
    f=changed.json()['fields'][0];assert f['id']==fid and f['purpose']=='food_shop'
    previous=client.get('/api/admin/content/types/'+t['id']+'/versions/1').json();assert previous['fields'][0]['name']=='原店名'


def test_food_field_upgrade_requires_csrf_and_long_shop_is_rejected_before_persistence(client):
    t=client.post('/api/admin/food/install-template',headers=csrf(client)).json()
    denied=client.post('/api/admin/food/types/'+t['type_id']+'/fields',json={'expected_type_revision':t['schema_version'],'expected_template_revision':t['revision'],'confirmation':'新增可选餐厅信息字段'})
    assert denied.status_code==403
    shop=next(f['field']['id'] for f in t['fields'] if f['field'].get('purpose')=='food_shop')
    bad={'type_id':t['type_id'],'schema_version':t['schema_version'],'template':{'id':t['id'],'version':t['version']},'title':'合成超长店名','body':'保留','display_date':'2026-11-05','status':'published','values':{shop:'长'*201}}
    assert write(client,'/records',bad).status_code==422


def test_a_food_marker_does_not_invent_travel_affiliation(client):
    t=make_type(client);title='source-kind-'+uuid.uuid4().hex
    plain=write(client,'/records',{**record_payload(t),'title':title,'body':'- @f 合成普通文章餐厅'}).json()
    assert client.get('/api/food',params={'q':title}).json()['items'][0]['travel_source'] is None
    changed=write(client,'/records/'+plain['id'],update_payload(plain,life={'start_date':'2026-10-03'}),'put');assert changed.status_code==200,changed.text
    assert client.get('/api/food',params={'q':title}).json()['items'][0]['travel_source']==title


@pytest.mark.parametrize('depth',[1,2,3])
@pytest.mark.parametrize('separator',['\n','\n\n'])
def test_visual_tight_nested_media_is_structural_not_paragraph_text(depth,separator):
    """TipTap serializes tight lists without a blank line before media."""
    from app.services.body_media import locations
    payload={'id':'11111111-1111-4111-8111-111111111111','alt':'合成照片','caption':'多级餐厅','width':720,'widthPercent':60,'align':'right','layout':'grid'}
    raw=':::lj-media-v1\n'+json.dumps(payload,ensure_ascii=False)+'\n:::'
    source='\n'.join('  '*i+'- @f 合成餐厅' for i in range(depth))+separator+'\n'.join('  '*depth+l for l in raw.splitlines())
    assert blocks(source,2)==[payload]
    assert locations(source,2)==[(depth+(1 if separator=='\n' else 2),payload)]


@pytest.mark.parametrize('depth',[1,2,3])
def test_tight_nested_media_still_rejects_invalid_attributes(depth):
    from fastapi import HTTPException
    source='\n'.join('  '*i+'- 层级' for i in range(depth))+'\n'+'\n'.join('  '*depth+l for l in media('not-a-uuid').splitlines())
    with pytest.raises(HTTPException) as failure:blocks(source,2)
    assert failure.value.status_code==422


@pytest.mark.parametrize('depth',[1,2,3])
def test_tight_list_restaurant_photos_save_reopen_and_reindex_without_cross_visit(client,depth):
    t=make_type(client);a=upload(client).json();b=upload(client).json();cover=upload(client).json()
    def visit(name,asset):
        lines=['  '*i+'- 上层' for i in range(depth-1)]
        lines+=['  '*(depth-1)+'- @f '+name]
        if asset:lines+=['  '*depth+l for l in media(asset['id']).splitlines()]
        return '\n'.join(lines)
    body='@l 合成地区\n\n'+'\n\n'.join([visit('重复餐厅',a),visit('另一餐厅',b),visit('重复餐厅',None),media(cover['id'])])
    title='v516-tight-'+uuid.uuid4().hex
    saved=write(client,'/records',{**record_payload(t),'body':body,'body_format':2,'title':title,'connections':{'media':[{'id':cover['id'],'cover':True}]}})
    assert saved.status_code==200,saved.text
    r=saved.json()
    reread=client.get('/api/admin/content/records/'+r['id']).json()
    assert reread['body']==body and set(reread['body_media_ids'])=={a['id'],b['id'],cover['id']}
    def visits():
        rows=client.get('/api/food',params={'q':title}).json()['items']
        assert len(rows)==3
        assert sorted(x['cover_id'] or '' for x in rows)==sorted([a['id'],b['id'],''])
        assert next(x for x in rows if x['name']=='另一餐厅')['cover_id']==b['id']
        assert all(x['source_kind']=='mark' for x in rows)
        for x in rows:assert client.get('/api/food/'+x['id']).json()['cover_id']==x['cover_id']
        return {x['id']:x['cover_id'] for x in rows}
    before=visits()
    after=str(uuid.UUID(int=uuid.UUID(r['id']).int-1))
    rebuilt=client.post('/api/admin/food/rebuild',params={'after':after},headers=csrf(client))
    assert rebuilt.status_code==200,rebuilt.text
    assert visits()==before
    updated=write(client,'/records/'+r['id'],update_payload(r,body_format=2),'put')
    assert updated.status_code==200,updated.text
    assert visits()==before
    with SessionLocal() as db:
        from app.content_models import RecordRevision
        assert db.get(RecordRevision,(r['id'],1)).snapshot['body']==body
        assert db.get(ContentRecord,r['id']).body==body


@pytest.mark.parametrize('sample',json.loads((__import__('pathlib').Path(__file__).parent/'fixtures/v516-private-list-serialization.json').read_text()))
def test_actual_tiptap_image_only_list_serialization_saves_and_invalid_update_preserves_body(client,sample):
    t=make_type(client);photo=upload(client).json();body=sample['output'].replace('11111111-1111-4111-8111-111111111111',photo['id'])
    payload={**record_payload(t),'title':'v516-actual-'+uuid.uuid4().hex,'body':body,'body_format':2}
    saved=write(client,'/records',payload);assert saved.status_code==200,saved.text;r=saved.json()
    reopened=client.get('/api/admin/content/records/'+r['id']).json();assert reopened['body']==body and reopened['body_media_ids']==[photo['id']]
    failed=write(client,'/records/'+r['id'],update_payload(r,body=body.replace(photo['id'],'invalid-uuid'),body_format=2),'put')
    assert failed.status_code==422
    after=client.get('/api/admin/content/records/'+r['id']).json()
    assert after['body']==body and after['revision']==r['revision'] and after['body_media_ids']==[photo['id']]
