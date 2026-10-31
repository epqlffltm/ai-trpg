# asset-server/tests/test_world_publishing.py

"""
세계관의 게시와 판(#591, 판의 형식 1)을 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 게시하면 판이 생긴다. 소개는 걸러지고(걸러 낸 것을 알린다), 인물마다 캐릭터의 마지막 판에서 story 에 쓰는 칸만
    복사한다(chat 에만 쓰는 칸은 없다). 보이기는 세계관의 기본을 채운 정해진 값이다. 로어북의 마지막 판도 복사한다
  - 판은 바뀌지 않는다. 캐릭터를 고쳐 다시 게시해도 이미 게시한 세계관의 판은 그대로다. 번호는 1, 2 로 오른다
  - 닿지 않는 장소는 알리기만 한다(warnings). 게시는 된다
  - 막는 것(409, 게시해 보기에도 같은 이름): 시작 장소, 시작 시간대, 인물이 없다. 장소, 시간대, 물건, 인물,
    호감도의 단계를 가리키는데 없다. 캐릭터를 지웠거나 게시한 적이 없거나, 전체이용가 세계관에 성인 캐릭터가 있다.
    로어북을 지웠거나 게시한 적이 없다. 남의 그림을 쓴다
  - 그림: 판에 쓰인 그림(대표, 소개, 장소, 물건, 인물의 그림)을 적는다. 공개 세계관의 판의 그림은 남도 본다.
    탈퇴하면 비공개 세계관은 판과 함께 지워지고, 남긴 공개 세계관의 판에 쓰인 그림은 남는다
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from app.worlds.documents import DOCUMENT_FORMAT
from app.worlds.models import World, WorldImageUse
from tests.images import FakeImageStore, StoredObject, own_image
from tests.signing import signed_withdrawal
from tests.worlds import (
    CHARACTERS_URL,
    LOREBOOKS_URL,
    OTHER,
    OWNER,
    STAGES,
    WORLDS_URL,
    bearer,
    character,
    check,
    create_world,
    full_world,
    member,
    publish,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

IMAGES_URL = f'{API_PREFIX}/images'
CITY = {'id': 'city', 'name': '가나폴리아', 'kind': 'place', 'keywords': ['수도'], 'content': '제국의 수도.'}


@pytest.fixture
def owner(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OWNER)


@pytest.fixture
def other(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OTHER, operator=False)


@pytest.fixture
def store(app: FastAPI) -> FakeImageStore:
    fake = FakeImageStore()
    app.state.image_store = fake
    return fake


async def two_characters(client: AsyncClient, headers: dict) -> tuple[dict, dict]:
    return await character(client, headers, '아리', greeting='안녕'), await character(client, headers, '버')


async def ready_world(client: AsyncClient, headers: dict, **fields) -> dict:
    ari, beo = await two_characters(client, headers)
    return await create_world(client, headers, {**full_world(ari['id'], beo['id']), **fields})


async def problems_of(client: AsyncClient, headers: dict, world: dict) -> list[str]:
    """게시해 보기와 게시가 같은 이름으로 막는지 보고, 그 이름들을 돌려준다."""
    checked = await check(client, headers, world)
    response = await publish(client, headers, world)
    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    assert response.json()['problems'] == checked['problems']
    assert checked['ready'] is False
    return checked['problems']


# --- 게시와 판 ---


async def test_publishing_freezes_the_world_into_version_one(client: AsyncClient, owner: dict):
    world = await ready_world(client, owner)

    response = await publish(client, owner, world)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    body = response.json()
    document = body['document']
    assert (body['number'], document['format'], document['name']) == (1, DOCUMENT_FORMAT, '여름 학원')
    assert document['intro_html'] == '<p>여름 방학의 학원.</p>'
    assert body['removed'] == [{'kind': 'tag', 'name': 'script'}]
    assert body['warnings'] == ['place_unreachable']
    assert (document['start_place'], document['start_slot'], document['deadline_days']) == ('school', 'morning', 30)
    assert [slot['id'] for slot in document['slots']] == ['morning', 'day', 'evening', 'night']
    assert document['start_items'] == [{'item': 'rose', 'count': 2}]


async def test_the_cast_copies_only_the_story_fields_of_each_character(client: AsyncClient, owner: dict):
    world = await ready_world(client, owner)

    document = (await publish(client, owner, world)).json()['document']

    ari, beo = document['cast']
    assert set(ari['character']) == {
        'id',
        'version',
        'name',
        'intro_html',
        'speech_examples',
        'age',
        'gender',
        'image_id',
        'sprites',
    }
    assert (ari['character']['name'], ari['character']['version']) == ('아리', 1)
    assert ari['character']['speech_examples'] == '아리의 말투'
    assert (ari['home'], ari['schedule'][0]['slot'], ari['affection']['gifts'][0]['item']) == (
        'library',
        'evening',
        'rose',
    )
    # 보이기: 아리는 공개만 덮어썼고 나머지는 세계관의 기본이다. 버는 지도만 덮어썼다
    assert (ari['reveal'], ari['map'], ari['panel']) == ('shown', 'hidden', ['intro', 'affection'])
    assert (beo['reveal'], beo['map'], beo['map_stage']) == ('silhouette', 'stage', '친함')
    assert beo['home'] is None


async def test_a_published_version_does_not_follow_the_character(client: AsyncClient, owner: dict):
    world = await ready_world(client, owner)
    await publish(client, owner, world)
    ari_id = world['cast'][0]['character_id']
    await client.patch(f'{CHARACTERS_URL}/{ari_id}', json={'name': '아리아'}, headers=owner)
    await client.post(f'{CHARACTERS_URL}/{ari_id}/versions', json={}, headers=owner)

    first = await client.get(f'{WORLDS_URL}/{world["id"]}/versions/1', headers=owner)
    second = (await publish(client, owner, world)).json()
    listed = await client.get(f'{WORLDS_URL}/{world["id"]}/versions', headers=owner)
    draft = await client.get(f'{WORLDS_URL}/{world["id"]}', headers=owner)

    assert first.json()['document']['cast'][0]['character']['name'] == '아리'
    assert second['number'] == 2
    assert (
        second['document']['cast'][0]['character']['name'],
        second['document']['cast'][0]['character']['version'],
    ) == (
        '아리아',
        2,
    )
    assert [item['number'] for item in listed.json()] == [2, 1]
    assert draft.json()['latest_version'] == 2


async def test_a_missing_version_number_is_not_found(client: AsyncClient, owner: dict):
    world = await ready_world(client, owner)

    response = await client.get(f'{WORLDS_URL}/{world["id"]}/versions/1', headers=owner)

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_the_check_is_ready_and_warns_without_making_a_version(client: AsyncClient, owner: dict):
    world = await ready_world(client, owner)

    checked = await check(client, owner, world)
    listed = await client.get(f'{WORLDS_URL}/{world["id"]}/versions', headers=owner)

    assert checked == {
        'ready': True,
        'problems': [],
        'warnings': ['place_unreachable'],
        'removed': [{'kind': 'tag', 'name': 'script'}],
    }
    assert listed.json() == []


async def test_a_fully_connected_map_has_no_warning(client: AsyncClient, owner: dict):
    paths = [{'a': 'school', 'b': 'library', 'minutes': 10}, {'a': 'library', 'b': 'roof', 'minutes': 5}]
    world = await ready_world(client, owner, paths=paths)

    assert (await check(client, owner, world))['warnings'] == []


async def test_lorebooks_are_copied_in_order(client: AsyncClient, owner: dict):
    made = (await client.post(LOREBOOKS_URL, json={'name': '제국', 'entries': [CITY]}, headers=owner)).json()
    await client.post(f'{LOREBOOKS_URL}/{made["id"]}/versions', json={}, headers=owner)
    world = await ready_world(client, owner, lorebooks=[made['id']])

    document = (await publish(client, owner, world)).json()['document']

    assert [(item['id'], item['version'], item['name']) for item in document['lorebooks']] == [(made['id'], 1, '제국')]


# --- 막는 것 ---


async def test_an_empty_world_lists_what_it_lacks(client: AsyncClient, owner: dict):
    world = await create_world(client, owner, {'genre': 'romance', 'name': '빈 세계'})

    assert await problems_of(client, owner, world) == ['start_place_missing', 'cast_empty']


async def test_a_start_slot_that_is_gone_blocks(client: AsyncClient, owner: dict):
    world = await ready_world(client, owner)
    await client.patch(f'{WORLDS_URL}/{world["id"]}', json={'start_slot': None}, headers=owner)

    assert await problems_of(client, owner, world) == ['start_slot_missing']


@pytest.mark.parametrize(
    ('changes', 'problem'),
    [
        ({'paths': [{'a': 'school', 'b': 'nowhere', 'minutes': 1}]}, 'place_missing'),
        # 시간대를 바꾸자 아리의 일정(저녁)이 없는 시간대를 가리킨다
        ({'slots': [{'id': 'am', 'name': '오전', 'start_hour': 6}], 'start_slot': 'am'}, 'slot_missing'),
        ({'start_items': [{'item': 'ghost', 'count': 1}]}, 'item_missing'),
    ],
)
async def test_pointing_at_what_is_not_there_blocks(client: AsyncClient, owner: dict, changes: dict, problem: str):
    world = await ready_world(client, owner)
    await client.patch(f'{WORLDS_URL}/{world["id"]}', json=changes, headers=owner)

    assert problem in await problems_of(client, owner, world)


@pytest.mark.parametrize(
    ('condition', 'problem'),
    [
        ({'kind': 'reach_place', 'target': 'moon'}, 'place_missing'),
        ({'kind': 'slot_is', 'target': 'dawn'}, 'slot_missing'),
        ({'kind': 'hold_item', 'target': 'ghost', 'count': 2}, 'item_missing'),
        ({'kind': 'gave_item', 'target': 'ari', 'value': 'ghost'}, 'item_missing'),
        ({'kind': 'accompanied', 'target': 'nobody'}, 'cast_target_missing'),
        ({'kind': 'affection_below', 'target': 'ari', 'value': '원수'}, 'stage_missing'),
        ({'kind': 'affection_at_least', 'target': 'nobody', 'value': '친함'}, 'cast_target_missing'),
    ],
)
async def test_a_schedule_condition_pointing_at_nothing_blocks(
    client: AsyncClient, owner: dict, condition: dict, problem: str
):
    ari, beo = await two_characters(client, owner)
    line = {'slot': 'day', 'place': 'school', 'when': {'match': 'any', 'items': [condition]}}
    body = full_world(ari['id'], beo['id'])
    body['cast'][1]['schedule'] = [line]
    world = await create_world(client, owner, body)

    assert problem in await problems_of(client, owner, world)


async def test_conditions_on_days_need_no_target(client: AsyncClient, owner: dict):
    ari, beo = await two_characters(client, owner)
    when = {'items': [{'kind': 'day_at_least', 'count': 3}, {'kind': 'day_at_most', 'count': 7}]}
    body = full_world(ari['id'], beo['id'])
    body['cast'][1]['schedule'] = [{'slot': 'night', 'place': 'roof', 'when': when}]
    world = await create_world(client, owner, body)

    assert (await check(client, owner, world))['problems'] == []


async def test_a_map_stage_must_be_one_of_the_stages(client: AsyncClient, owner: dict):
    ari, beo = await two_characters(client, owner)
    body = full_world(ari['id'], beo['id'])
    body['cast'][1] = member('beo', beo['id'], map='stage')
    world = await create_world(client, owner, body)
    wrong = await create_world(
        client, owner, {**body, 'cast': [body['cast'][0], member('beo', beo['id'], map_stage='?')]}
    )

    assert await problems_of(client, owner, world) == ['stage_missing']
    assert await problems_of(client, owner, wrong) == ['stage_missing']


async def test_a_default_stage_map_needs_a_stage_for_everyone(client: AsyncClient, owner: dict):
    world = await ready_world(client, owner, show={'map': 'stage'})

    # 아리는 지도를 덮어쓰지 않아 기본(stage)을 따르는데 단계를 고르지 않았다
    assert await problems_of(client, owner, world) == ['stage_missing']


async def test_characters_that_cannot_be_copied_block(client: AsyncClient, owner: dict):
    unpublished = await character(client, owner, '초안', published=False)
    gone = await character(client, owner, '사라짐')
    body = full_world(unpublished['id'], gone['id'])
    world = await create_world(client, owner, body)
    await client.delete(f'{CHARACTERS_URL}/{gone["id"]}', headers=owner)

    assert await problems_of(client, owner, world) == ['character_unpublished', 'character_missing']


async def test_an_adult_character_does_not_go_into_an_all_ages_world(client: AsyncClient, owner: dict):
    adult = await character(client, owner, '밤', rating='adult')
    beo = await character(client, owner, '버')
    world = await create_world(client, owner, full_world(adult['id'], beo['id']))
    grown = await create_world(client, owner, {**full_world(adult['id'], beo['id']), 'rating': 'adult'})

    assert await problems_of(client, owner, world) == ['character_rating_too_high']
    assert (await publish(client, owner, grown)).status_code == status.HTTP_201_CREATED


async def test_lorebooks_that_cannot_be_copied_block(client: AsyncClient, owner: dict):
    unpublished = (await client.post(LOREBOOKS_URL, json={'name': '초안'}, headers=owner)).json()
    gone = (await client.post(LOREBOOKS_URL, json={'name': '사라짐'}, headers=owner)).json()
    world = await ready_world(client, owner, lorebooks=[unpublished['id'], gone['id']])
    await client.delete(f'{LOREBOOKS_URL}/{gone["id"]}', headers=owner)

    assert await problems_of(client, owner, world) == ['lorebook_unpublished', 'lorebook_missing']


async def test_someone_elses_image_in_the_intro_blocks(client: AsyncClient, owner: dict, session: AsyncSession):
    theirs = await own_image(session, OTHER)
    world = await ready_world(client, owner, intro_html=f'<img src="/api/v1/asset/images/{theirs}" alt="x">')

    assert await problems_of(client, owner, world) == ['image_not_owned']


# --- 그림 ---


async def test_publishing_records_every_image_of_the_version(client: AsyncClient, owner: dict, session: AsyncSession):
    cover, place, thing, face, sprite = [await own_image(session, OWNER) for _ in range(5)]
    ari = await character(
        client, owner, '아리', image_id=face, sprites=[{'id': 'base', 'image_id': sprite, 'expression': ''}]
    )
    beo = await character(client, owner, '버')
    body = full_world(ari['id'], beo['id'])
    body['places'][1] = {'id': 'library', 'name': '도서관', 'backgrounds': {'night': place}}
    body['items'] = [{'id': 'rose', 'name': '장미', 'image_id': thing}]
    world = await create_world(client, owner, {**body, 'image_id': cover})

    version = (await publish(client, owner, world)).json()

    used = await session.scalars(
        select(WorldImageUse.image_id).where(WorldImageUse.version_id == uuid.UUID(version['id']))
    )
    assert {str(image_id) for image_id in used} == {cover, place, thing, face, sprite}


async def test_a_public_worlds_images_are_seen_by_others(
    client: AsyncClient, owner: dict, other: dict, session: AsyncSession, store: FakeImageStore
):
    cover = await own_image(session, OWNER)
    world = await ready_world(client, owner, image_id=cover)
    await publish(client, owner, world)

    private = (await client.get(f'{IMAGES_URL}/{cover}', headers=other)).status_code
    await client.patch(f'{WORLDS_URL}/{world["id"]}', json={'visibility': 'public'}, headers=owner)
    public = (await client.get(f'{IMAGES_URL}/{cover}', headers=other)).status_code

    assert (private, public) == (status.HTTP_404_NOT_FOUND, status.HTTP_200_OK)


async def test_withdrawal_drops_private_worlds_and_keeps_public_world_images(
    client: AsyncClient, owner: dict, session: AsyncSession, store: FakeImageStore
):
    kept, dropped = [await own_image(session, OWNER) for _ in range(2)]
    for image_id in (kept, dropped):
        store.objects[image_id] = StoredObject(b'bytes', 'image/png')
    public = await ready_world(client, owner, image_id=kept)
    await client.patch(f'{WORLDS_URL}/{public["id"]}', json={'visibility': 'public'}, headers=owner)
    await publish(client, owner, public)
    private = await create_world(client, owner, {'genre': 'romance', 'name': '비밀', 'image_id': dropped})

    response = await signed_withdrawal(client, str(OWNER))

    session.expire_all()
    assert response.status_code == status.HTTP_200_OK
    assert await session.get(World, uuid.UUID(private['id'])) is None
    assert await session.get(World, uuid.UUID(public['id'])) is not None
    assert set(store.objects) == {kept}


async def test_stages_are_kept_in_the_cast(client: AsyncClient, owner: dict):
    world = await ready_world(client, owner)

    document = (await publish(client, owner, world)).json()['document']

    assert [stage['name'] for stage in document['cast'][0]['affection']['stages']] == [
        stage['name'] for stage in STAGES
    ]
    assert document['cast'][0]['affection']['start'] == 10
