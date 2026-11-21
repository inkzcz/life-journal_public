"""Synthetic API/database regression: one Markdown interpretation for all consumers."""
import uuid
import hashlib
import pytest
from sqlalchemy import select
from test_content import client, make_type, record_payload, update_payload, write
from test_api import SessionLocal, csrf, reset_limiter
from app.archive_models import Place, RecordMarkedPlace, RecordPlace
from app.content_models import ContentRecord, RecordRevision
from app.v5_models import FoodOccurrence


def save(c, t, body, **changes):
    response = write(c, '/records', {**record_payload(t), 'body': body, **changes})
    assert response.status_code == 200, response.text
    return response.json()


def foods(id):
    with SessionLocal() as db:
        return [dict(id=f.id, key=f.source_key, name=f.name, place_id=f.place_id,
                     city=f.city_override if f.city_override is not None else f.city,
                     description=f.description, day=f.day, revision=f.revision)
                for f in db.scalars(select(FoodOccurrence).where(
                    FoodOccurrence.record_id == id, FoodOccurrence.active.is_(True)).order_by(FoodOccurrence.day, FoodOccurrence.name, FoodOccurrence.id))]


@pytest.mark.parametrize('body', [
    '@l 成都\n@f 测试餐厅',
    '@l **成都**\n\n@f **测试餐厅**',
    '@l *成都*\n\n@f _测试餐厅_',
    '普通段落 @l 成都 @f 测试餐厅',
    '- @l 成都\n- @f **测试餐厅**',
    '1. @l 成都\n2. @f 测试餐厅',
    '- 旅行\n  - @l 成都\n  - @f **测试餐厅**',
    '@l 成都\n\n## 10月3日\n\n- @f 测试餐厅',
    '@l 成都  \n@f 测试餐厅',
])
def test_saved_marks_always_have_same_place_in_food_and_connections(client, body):
    t = make_type(client)
    r = save(client, t, body)
    assert r['body'] == body
    assert {p['name'] for p in r['connections']['places']} == {'成都', '测试餐厅'}
    f, = foods(r['id'])
    restaurant = next(p for p in r['connections']['places'] if p['name'] == '测试餐厅')
    assert f['place_id'] == restaurant['id'] and f['city'] == '成都'
    with SessionLocal() as db:
        assert db.get(RecordPlace, (r['id'], f['place_id']))
        assert len(list(db.scalars(select(RecordMarkedPlace).where(RecordMarkedPlace.record_id == r['id'])))) == 2
    again = write(client, '/records/' + r['id'], update_payload(r), 'put')
    assert again.status_code == 200, again.text
    assert foods(r['id'])[0]['id'] == f['id']
    assert {p['id'] for p in again.json()['connections']['places']} == {p['id'] for p in r['connections']['places']}
    assert client.get('/api/admin/content/records/' + r['id']).json()['body'] == body


EXAMPLE = ('10月3日\n\n@l 汉源县\n\n- @f **游记黄牛肉火锅**\n'
           '  - 从家出发，中午途经汉源县。\n  - 黄牛肉火锅味道不错。\n\n'
           '10月4日\n\n@l 成都\n\n- @f 陈麻婆豆腐\n  - 晚餐体验不错。')


def test_acceptance_example_dates_activities_draft_publish_and_removal(client):
    t = make_type(client)
    r = save(client, t, EXAMPLE, status='draft', life={'start_date': '2026-10-03'})
    initial = foods(r['id'])
    assert len(initial) == 2
    assert [(f['city'], str(f['day'])) for f in initial] == [('汉源县', '2026-10-03'), ('成都', '2026-10-04')]
    assert not r['life']['activities']  # Drafts index marks without regenerating itinerary.
    assert '黄牛肉火锅味道不错。' in initial[0]['description']
    assert client.get('/api/food?q=' + r['title']).status_code == 200
    published = write(client, '/records/' + r['id'], update_payload(r, status='published'), 'put')
    assert published.status_code == 200, published.text
    r = published.json()
    assert r['body'] == EXAMPLE
    activities = [a for a in r['life']['activities'] if a['kind'] == 'food']
    assert [(a['place_id'], a['day']) for a in activities] == [(f['place_id'], str(f['day'])) for f in initial]
    body = '10月4日\n\n@l 成都\n\n- @f 陈麻婆豆腐\n  - 晚餐体验不错。'
    changed = write(client, '/records/' + r['id'], update_payload(r, body=body, life=r['life']), 'put')
    assert changed.status_code == 200, changed.text
    assert len(foods(r['id'])) == 1
    from test_markdown_travel import reconcile
    remaining = reconcile(client,changed.json())
    assert {p['name'] for p in remaining['connections']['places']} == {'成都', '陈麻婆豆腐'}
    with SessionLocal() as db:
        assert db.get(RecordRevision, (r['id'], 1)).snapshot['body'] == EXAMPLE
        assert all(db.get(Place, f['place_id']) for f in initial)
    removed = client.request('DELETE', '/api/admin/content/records/' + r['id'], headers=csrf(client), json={'expected_revision': remaining['revision']})
    assert removed.status_code == 200
    assert not foods(r['id'])


def test_code_and_media_are_inert_and_nested_descriptions_do_not_bleed(client):
    body = ('@l 成都\n\n- @f **甲餐厅**\n  - 好吃\n  - 第二句\n'
            '- @f 乙餐厅\n  - 另一家\n\n`@f 行内代码`\n\n'
            '```markdown\n@l 围栏城市\n@f 围栏餐厅\n```\n\n    @f 缩进代码\n')
    r = save(client, make_type(client), body)
    assert {p['name'] for p in r['connections']['places']} == {'成都', '甲餐厅', '乙餐厅'}
    f = {f['name']: f for f in foods(r['id'])}
    assert f['甲餐厅']['description'] == '好吃\n第二句'
    assert f['乙餐厅']['description'] == '另一家'


def test_softbreak_list_description_does_not_become_part_of_a_place_name(client):
    body = '@l 成都\n\n- @f **软换行餐厅**\n  很好吃\n  第二句\n- @f 下一家\n  不串行'
    r = save(client, make_type(client), body)
    f = {f['name']: f for f in foods(r['id'])}
    assert f['软换行餐厅']['description'] == '很好吃\n第二句'
    assert f['下一家']['description'] == '不串行'
    assert {p['name'] for p in r['connections']['places']} == {'成都', '软换行餐厅', '下一家'}


def test_plain_article_date_before_publication_does_not_jump_to_next_year(client):
    r = save(client, make_type(client), '10月3日\n\n@f **普通文章餐厅**', display_date='2026-10-18')
    f, = foods(r['id'])
    assert str(f['day']) == '2026-10-03'
    assert not r['life']['start_date'] and not r['life']['activities']


def test_explicit_identity_two_cities_and_manual_city_survive(client):
    ids = []
    restaurant = '同名-' + uuid.uuid4().hex
    for city in ['成都', '汉源']:
        response = client.post('/api/admin/archive/places', headers=csrf(client), json={'name': restaurant, 'city': city, 'category': '餐厅'})
        assert response.status_code == 200, response.text
        ids.append(response.json()['id'])
    body = f'@l 成都\n\n- @f **{restaurant}** {{#place:{ids[0]}}}\n\n## 第2天\n\n@l 汉源\n\n- @f {restaurant} {{#place:{ids[1]}}}'
    r = save(client, make_type(client), body, life={'start_date': '2026-10-03'})
    f = foods(r['id']); assert {x['place_id'] for x in f} == set(ids)
    assert {x['city'] for x in f} == {'成都', '汉源'}
    response = client.put('/api/admin/food/occurrences/' + f[0]['id'], headers=csrf(client), json={'expected_revision': f[0]['revision'], 'city_override': '人工修正', 'category': '保留'})
    assert response.status_code == 200
    changed = write(client, '/records/' + r['id'], update_payload(r, life=r['life']), 'put')
    assert changed.status_code == 200, changed.text
    assert next(x for x in foods(r['id']) if x['id'] == f[0]['id'])['city'] == '人工修正'


def test_same_name_in_two_regions_stays_distinct_and_reuses_proven_places(client):
    name = '同名分店-' + uuid.uuid4().hex
    body = f'@l 成都\n\n@f {name}\n\n## 第二站\n\n@l 汉源\n\n@f **{name}**'
    t = make_type(client)
    first = save(client, t, body)
    first_food = foods(first['id'])
    assert len({f['place_id'] for f in first_food}) == 2
    second = save(client, t, body)
    assert {f['city']: f['place_id'] for f in foods(second['id'])} == {f['city']: f['place_id'] for f in first_food}


def test_formatted_deleted_place_cannot_resurrect(client):
    name = '已删除格式化-' + uuid.uuid4().hex
    p = client.post('/api/admin/archive/places', headers=csrf(client), json={'name': name, 'category': '餐厅'}).json()
    response = client.request('DELETE', '/api/admin/archive/places/' + p['id'], headers=csrf(client), json={'expected_revision': p['revision']})
    assert response.status_code == 200, response.text
    t = make_type(client)
    response = write(client, '/records', {**record_payload(t), 'body': '@f **' + name + '**'})
    assert response.status_code == 422 and '删除' in response.text
    with SessionLocal() as db:
        assert db.get(Place, p['id']) is None
        assert not db.scalar(select(Place).where(Place.name == name))
        assert not db.scalar(select(ContentRecord).where(ContentRecord.type_id == t['id']))


def test_failed_binding_rolls_back_article_places_food_and_revision(client):
    t = make_type(client)
    body = '@l 回滚城市-' + uuid.uuid4().hex + '\n\n@f 不存在 {#place:' + str(uuid.uuid4()) + '}'
    response = write(client, '/records', {**record_payload(t), 'body': body})
    assert response.status_code == 422
    with SessionLocal() as db:
        assert not db.scalar(select(ContentRecord).where(ContentRecord.type_id == t['id']))
        assert not db.scalar(select(Place).where(Place.name == body.splitlines()[0][3:]))


def test_failure_after_food_sync_rolls_back_all_new_resources(client, monkeypatch):
    from fastapi import HTTPException
    from app.services import food
    original = food.sync
    seen = []
    def fail_after_sync(db, record):
        original(db, record)
        seen.append(record.id)
        raise HTTPException(422, '合成同步故障')
    monkeypatch.setattr(food, 'sync', fail_after_sync)
    city = '事务城市-' + uuid.uuid4().hex
    t = make_type(client)
    response = write(client, '/records', {**record_payload(t), 'body': f'@l {city}\n\n@f 事务餐厅'})
    assert response.status_code == 422 and len(seen) == 1
    with SessionLocal() as db:
        assert db.get(ContentRecord, seen[0]) is None
        assert not db.scalar(select(Place).where(Place.name == city))
        for model in [FoodOccurrence, RecordMarkedPlace, RecordPlace, RecordRevision]:
            assert not db.scalar(select(model).where(model.record_id == seen[0]))


def test_legacy_heading_reset_row_keeps_id_key_and_manual_override(client):
    name = '旧索引-' + uuid.uuid4().hex
    body = '@l 成都\n\n## 10月3日\n\n- @f ' + name
    r = save(client, make_type(client), body)
    old_key = 'mark:' + hashlib.sha256((name + '|').encode()).hexdigest() + ':1'
    old_id = str(uuid.uuid5(uuid.UUID(r['id']), 'food:' + old_key))
    with SessionLocal() as db:
        f = db.scalar(select(FoodOccurrence).where(FoodOccurrence.record_id == r['id']))
        f.id = old_id; f.source_key = old_key; f.place_id = None
        f.city = ''; f.city_override = '人工历史城市'; f.category = '历史分类'
        db.commit()
    for _ in range(2):
        response = write(client, '/records/' + r['id'], update_payload(r), 'put')
        assert response.status_code == 200, response.text
        r = response.json()
        f, = foods(r['id'])
        assert (f['id'], f['key'], f['city']) == (old_id, old_key, '人工历史城市')
        assert f['place_id'] in {p['id'] for p in r['connections']['places']}
    with SessionLocal() as db:
        assert db.get(FoodOccurrence, old_id).category == '历史分类'
        assert len(list(db.scalars(select(FoodOccurrence).where(FoodOccurrence.record_id == r['id'])))) == 1


def test_legacy_unbound_row_is_not_guessed_into_a_different_city(client):
    name = '不猜身份-' + uuid.uuid4().hex
    body = '@l 成都\n\n## 日期\n\n@f ' + name
    r = save(client, make_type(client), body)
    old_key = 'mark:' + hashlib.sha256((name + '|').encode()).hexdigest() + ':1'
    with SessionLocal() as db:
        f = db.scalar(select(FoodOccurrence).where(FoodOccurrence.record_id == r['id']))
        old_id = f.id; f.source_key = old_key; f.place_id = None; f.city_override = '成都人工修正'
        db.commit()
    response = write(client, '/records/' + r['id'], update_payload(r, body=body.replace('成都', '汉源')), 'put')
    assert response.status_code == 200, response.text
    f, = foods(r['id'])
    assert f['id'] != old_id and f['city'] == '汉源'
    with SessionLocal() as db:
        old = db.get(FoodOccurrence, old_id)
        assert not old.active and old.city_override == '成都人工修正'


@pytest.mark.parametrize('body', ['@l 成`都`', '@f 餐厅 <b>分店</b>', '@f 餐厅 ![图片](https://example.invalid/a.jpg)'])
def test_unsupported_name_format_rejects_without_partial_places(client, body):
    t = make_type(client)
    response = write(client, '/records', {**record_payload(t), 'body': body})
    assert response.status_code == 422
    with SessionLocal() as db:
        assert not db.scalar(select(ContentRecord).where(ContentRecord.type_id == t['id']))


def test_explicit_uuid_and_ambiguity_protect_current_save_atomically(client):
    name = '歧义-' + uuid.uuid4().hex
    for _ in range(2):
        response = client.post('/api/admin/archive/places', headers=csrf(client), json={'name': name, 'category': '餐厅'})
        assert response.status_code == 200
    t = make_type(client)
    r = save(client, t, '安全正文')
    response = write(client, '/records/' + r['id'], update_payload(r, body='@f **' + name + '**'), 'put')
    assert response.status_code == 422
    current = client.get('/api/admin/content/records/' + r['id']).json()
    assert current['body'] == r['body'] and current['revision'] == r['revision']
    with SessionLocal() as db:
        assert not db.get(RecordRevision, (r['id'], r['revision'] + 1))
        assert not list(db.scalars(select(RecordMarkedPlace).where(RecordMarkedPlace.record_id == r['id'])))
    response = client.get('/api/admin/archive/places', params={'q': name})
    assert response.status_code == 200
    pid = response.json()['items'][0]['id']
    valid = save(client, t, f'@f **{name}** {{#place:{pid}}}')
    assert foods(valid['id'])[0]['place_id'] in {p['id'] for p in valid['connections']['places']}


def test_shared_positions_and_existing_source_keys_are_stable():
    from app.services.markdown_marks import parse
    from app.services.marked_places import key
    body = '前言\n\n- @l **成都**\n  - @f *餐厅*'
    a, b = parse(body).marks
    assert (a['line'], a['column'], a['offset']) == (3, 3, body.index('@l'))
    assert (b['line'], b['column'], b['offset']) == (4, 5, body.index('@f'))
    assert b['region'] == '成都'
    assert key(b, b['region']) == hashlib.sha256('f|成都|餐厅|'.encode()).hexdigest()


def test_current_formatted_history_can_restore_without_reinterpreting_identity(client):
    r = save(client, make_type(client), '@l **成都**\n\n- @f **修订餐厅**')
    old_food, = foods(r['id'])
    changed = write(client, '/records/' + r['id'], update_payload(r, body='新的正文'), 'put').json()
    restored = client.post('/api/admin/recovery/history/' + r['id'] + '/1/restore', headers=csrf(client), json={'expected_revision': changed['revision'], 'scope': 'full', 'confirmation': '恢复为新草稿'})
    assert restored.status_code == 200, restored.text
    assert restored.json()['body'] == r['body']
    assert restored.json()['marked_places'] == r['marked_places']
    assert foods(r['id'])[0]['id'] == old_food['id']
