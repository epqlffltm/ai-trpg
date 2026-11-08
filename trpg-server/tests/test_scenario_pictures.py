# trpg-server/tests/test_scenario_pictures.py

"""
로어 항목마다의 그림(#1163)을 검증한다. 장소의 배경, 인물의 그림, 사건의 컷신이다. asset 서버는 가짜다.

맵과 픽스처는 tests/test_happenings.py 의 것이다(성문 시작, 광장, 숨긴 지하실, 사건 항목 셋, 물약).
여기에 인물 하나(문지기)를 성문에 둔다.

보는 것.
  - 시나리오: 그림을 저장하고 판에 굳힌다. 남의 그림이나 없는 그림은 422(pictures.image_id), 같은 항목이 둘이면 422 다.
    붙인 로어북에 없는 항목, 장소·인물·사건이 아닌 항목의 그림은 게시하지 못한다(409).
  - 테이블: 보일 때만 그림의 id 가 나간다. 아는 장소(map.places), 장면의 인물(.../rounds/current/people),
    일어난 사건(happening_occurred). 모르는 장소의 그림은 나가지 않는다. 앉은 사람은 그 그림을 받는다.
  - 쓰는 그림은 지우지 못한다.
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient

from app.assets.scenarios.snapshot import read_snapshot
from app.main import API_PREFIX
from app.portraits.seats import entry_pictures, picture_of, table_portraits, with_cutscene
from tests import test_happenings as happenings
from tests import test_table_map as map_tables
from tests.asset_server import FakeAsset
from tests.narration_model import asset_body
from tests.test_map_actions import going, play
from tests.test_table_items import SCENARIOS_URL, bearer, events_of, post, read_table, table_url

pytestmark = pytest.mark.usefixtures('clean_tables')

me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore
more = happenings.more

PORTRAITS_URL = f'{API_PREFIX}/portraits'
PICTURE = b'\x89PNG castle gate'


@pytest.fixture
def asset(app: FastAPI) -> FakeAsset:
    fake = FakeAsset()
    app.state.asset = fake
    return fake


@pytest.fixture
async def guard(client: AsyncClient, me: dict, more: dict) -> dict:
    """같은 로어북의 인물 항목 하나(문지기)."""
    url = f'{map_tables.LOREBOOKS_URL}/{more["lorebook"]["id"]}/entries'
    return await post(client, url, me, name='문지기', keywords=['문지기'], content='성문을 지킨다.', kind='person')


async def upload(client: AsyncClient, headers: dict) -> str:
    response = await client.post(PORTRAITS_URL, content=PICTURE, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['id']


def picture(entry: dict, image_id: str) -> dict:
    return {'entry_id': entry['id'], 'image_id': image_id}


async def draft(client: AsyncClient, me: dict, more: dict, pictures: list[dict], **fields) -> dict:
    """그 그림들을 적은 시나리오. 맵은 the_map, 사건은 함정이다. 게시하지 않았다."""
    rulebook = await post(client, map_tables.RULEBOOKS_URL, me, title='룰북')
    body = {
        'title': '성의 모험',
        'rulebook_id': rulebook['id'],
        'openings': ['성문 앞이다.'],
        'default_sheet': map_tables.SHEET,
        'lorebook_ids': [more['lorebook']['id']],
        **map_tables.the_map(more),
        'happenings': [happenings.trap(more)],
        'pictures': pictures,
        **fields,
    }
    return await post(client, SCENARIOS_URL, me, **body)


# --- 시나리오 ---


@pytest.mark.usefixtures('asset')
async def test_pictures_are_saved_and_published(client: AsyncClient, me: dict, more: dict):
    image_id = await upload(client, me)
    scenario = await draft(client, me, more, [picture(more['gate'], image_id), picture(more['trap'], image_id)])

    response = await happenings.publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    # 하루의 때마다의 배경을 적지 않았다
    assert scenario['pictures'] == [
        {**picture(more['gate'], image_id), 'by_time': {}},
        {**picture(more['trap'], image_id), 'by_time': {}},
    ]
    published = read_snapshot(response.json()['snapshot']).pictures
    assert [(one.entry_id, one.image_id) for one in published] == [
        (uuid.UUID(more['gate']['id']), uuid.UUID(image_id)),
        (uuid.UUID(more['trap']['id']), uuid.UUID(image_id)),
    ]


@pytest.mark.usefixtures('asset')
async def test_someone_elses_or_a_missing_picture_is_refused(client: AsyncClient, me: dict, friend: dict, more: dict):
    theirs = await upload(client, friend)
    body = {'title': '성의 모험', 'pictures': [picture(more['gate'], theirs)]}

    foreign = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)
    body['pictures'] = [picture(more['gate'], str(uuid.uuid4()))]
    missing = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert foreign.status_code == missing.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'pictures.image_id' in foreign.json()['detail']
    assert 'pictures.image_id' in missing.json()['detail']


@pytest.mark.usefixtures('asset')
async def test_one_entry_has_one_picture(client: AsyncClient, me: dict, more: dict):
    image_id = await upload(client, me)
    body = {'title': '성의 모험', 'pictures': [picture(more['gate'], image_id), picture(more['gate'], image_id)]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(('case', 'problem'), [('missing', 'picture_entry_missing'), ('item', 'picture_wrong_kind')])
@pytest.mark.usefixtures('asset')
async def test_a_picture_must_be_of_a_place_a_person_or_an_event(
    client: AsyncClient, me: dict, more: dict, case: str, problem: str
):
    image_id = await upload(client, me)
    entry = {'missing': {'id': str(uuid.uuid4())}, 'item': more['potion']}[case]
    scenario = await draft(client, me, more, [picture(entry, image_id)])

    response = await happenings.publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == [problem]


@pytest.mark.usefixtures('asset')
async def test_a_picture_in_use_cannot_be_deleted(client: AsyncClient, me: dict, more: dict):
    image_id = await upload(client, me)
    scenario = await draft(client, me, more, [picture(more['gate'], image_id)])

    refused = await client.delete(f'{PORTRAITS_URL}/{image_id}', headers=me)

    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['scenarios'] == [{'id': scenario['id'], 'title': '성의 모험'}]


# --- 테이블 ---


async def start(client: AsyncClient, me: dict, friend: dict, more: dict, guard: dict, pictures: list[dict]) -> dict:
    """그 그림들의 판으로 둘이 앉아 시작한 테이블. 문지기는 성문에 있다. 함정은 광장에 닿으면 일어난다."""
    table = await map_tables.open_duo(
        client,
        me,
        friend,
        more,
        **map_tables.the_map(more),
        happenings=[happenings.trap(more)],
        npc_places=[{'entry_id': guard['id'], 'place_id': more['gate']['id']}],
        default_npc_sheet=map_tables.SHEET,
        pictures=pictures,
    )
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


def place_pictures(table: dict) -> dict[str, str | None]:
    return {place['name']: place['image_id'] for place in table['map']['places']}


@pytest.mark.usefixtures('asset')
async def test_only_what_is_seen_shows_its_picture(
    client: AsyncClient, me: dict, friend: dict, more: dict, guard: dict, narrated
):
    gate, cellar, face, fall = [await upload(client, me) for _ in range(4)]
    pictures = [
        picture(more['gate'], gate),
        picture(more['cellar'], cellar),
        picture(guard, face),
        picture(more['trap'], fall),
    ]
    table = await start(client, me, friend, more, guard, pictures)

    # 처음에는 성문과 이어진 곳만 안다. 숨긴 지하실은 모른다. 함정은 아직 일어나지 않았다
    seen = await read_table(client, friend, table)
    assert place_pictures(seen)['성문'] == gate
    assert '지하실' not in place_pictures(seen)
    people = (await client.get(table_url(table, '/rounds/current/people'), headers=friend)).json()['people']
    assert [(person['name'], person['image_id']) for person in people] == [('문지기', face)]
    assert await events_of(client, friend, table, 'happening_occurred') == []

    await play(client, me, friend, table, narrated, mine=going(more['square']))

    # 함정이 일어나 지하실로 떨어졌다. 지하실을 알게 되고, 사건의 컷신이 이벤트에 있다
    seen = await read_table(client, friend, table)
    assert place_pictures(seen)['지하실'] == cellar
    (occurred,) = await events_of(client, friend, table, 'happening_occurred')
    assert occurred['payload']['image_id'] == fall


@pytest.mark.usefixtures('asset')
async def test_the_seated_get_the_pictures_of_the_table(
    client: AsyncClient, me: dict, friend: dict, more: dict, guard: dict, signing_key
):
    gate = await upload(client, me)
    table = await start(client, me, friend, more, guard, [picture(more['gate'], gate)])
    stranger = bearer(signing_key, uuid.UUID('33333333-2222-4333-8444-555555555555'))

    seated = await client.get(table_url(table, f'/portraits/{gate}/image'), headers=friend)
    outsider = await client.get(table_url(table, f'/portraits/{gate}/image'), headers=stranger)

    assert (seated.status_code, seated.content) == (status.HTTP_200_OK, PICTURE)
    assert outsider.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.usefixtures('asset')
async def test_a_place_without_a_picture_shows_none(client: AsyncClient, me: dict, friend: dict, more: dict, guard):
    table = await start(client, me, friend, more, guard, [])

    seen = await read_table(client, friend, table)
    people = (await client.get(table_url(table, '/rounds/current/people'), headers=friend)).json()['people']

    assert set(place_pictures(seen).values()) == {None}
    assert [person['image_id'] for person in people] == [None]


# --- 작은 함수들 ---

GATE = uuid.UUID('00000000-0000-4000-8000-0000000000a1')
TRAP = uuid.UUID('00000000-0000-4000-8000-0000000000a2')
IMAGE = uuid.UUID('00000000-0000-4000-8000-0000000000b1')
FACE = uuid.UUID('00000000-0000-4000-8000-0000000000b2')
CONTENT = {
    'pregens': [{'name': '엘프', 'image_id': str(FACE)}, {'name': '영애'}],
    'pictures': [{'entry_id': str(GATE), 'image_id': str(IMAGE)}],
}


def test_the_table_serves_the_pregens_and_the_pictures():
    assert entry_pictures(CONTENT) == {GATE: IMAGE}
    assert table_portraits(CONTENT) == {FACE, IMAGE}
    assert entry_pictures({}) == {}


def test_a_picture_is_found_by_its_entry():
    assert (picture_of(CONTENT, GATE), picture_of(CONTENT, str(GATE))) == (IMAGE, IMAGE)
    assert (picture_of(CONTENT, TRAP), picture_of(CONTENT, None)) == (None, None)


def test_a_cutscene_is_put_on_the_event():
    content = {'pictures': [{'entry_id': str(TRAP), 'image_id': str(IMAGE)}]}

    assert with_cutscene(content, {'entry_id': str(TRAP), 'name': '함정'}) == {
        'entry_id': str(TRAP),
        'name': '함정',
        'image_id': str(IMAGE),
    }
    assert with_cutscene(content, {'entry_id': str(GATE)})['image_id'] is None
