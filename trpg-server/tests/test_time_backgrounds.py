# trpg-server/tests/test_time_backgrounds.py

"""
장소의 하루의 때마다의 배경(#1163)을 검증한다. 로어 항목마다의 그림(pictures)의 by_time 칸이다. asset 서버는 가짜다.

맵과 픽스처는 tests/test_scenario_pictures.py 의 것이다(성문 시작, 광장, 문지기). 판의 시계는 기본(1일째 8시, 아침)이다.

보는 것.
  - 시나리오: 때마다의 그림을 저장하고 판에 굳힌다. 남의 그림이면 422(pictures.image_id), 모르는 때면 422,
    장소가 아닌 항목에 적으면 게시하지 못한다(409 picture_time_not_place).
  - 테이블: 아는 장소의 image_id 는 테이블의 시계의 지금 때의 그림이고, 그때의 그림이 없으면 기본 그림이다.
    앉은 사람은 때마다의 그림도 받는다.
  - 쓰는 그림은 때마다의 그림이라도 지우지 못한다.
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient

from app.assets.scenarios.snapshot import read_snapshot
from app.calendar.clock import TimeOfDay
from app.portraits.seats import place_picture, table_portraits, timed_pictures
from tests import test_happenings as happenings
from tests import test_scenario_pictures as pictured
from tests.narration_model import asset_body
from tests.test_table_items import SCENARIOS_URL, read_table, table_url
from tests.test_table_map import SHEET

pytestmark = [pytest.mark.usefixtures('clean_tables'), pytest.mark.usefixtures('asset')]

me = pictured.me
friend = pictured.friend
lore = pictured.lore
more = pictured.more
guard = pictured.guard
asset = pictured.asset


def timed(entry: dict, image_id: str, **by_time: str) -> dict:
    return {'entry_id': entry['id'], 'image_id': image_id, 'by_time': by_time}


# --- 시나리오 ---


async def test_backgrounds_by_time_are_saved_and_published(client: AsyncClient, me: dict, more: dict):
    day, night = await pictured.upload(client, me), await pictured.upload(client, me)
    scenario = await pictured.draft(client, me, more, [timed(more['gate'], day, night=night)])

    response = await happenings.publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert scenario['pictures'] == [{'entry_id': more['gate']['id'], 'image_id': day, 'by_time': {'night': night}}]
    (published,) = read_snapshot(response.json()['snapshot']).pictures
    assert published.by_time == {TimeOfDay.NIGHT: uuid.UUID(night)}


async def test_someone_elses_background_or_an_unknown_time_is_refused(
    client: AsyncClient, me: dict, friend: dict, more: dict
):
    mine, theirs = await pictured.upload(client, me), await pictured.upload(client, friend)
    body = {'title': '성의 모험', 'pictures': [timed(more['gate'], mine, night=theirs)]}

    foreign = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)
    body['pictures'] = [timed(more['gate'], mine, noon=mine)]
    unknown = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert foreign.status_code == unknown.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'pictures.image_id' in foreign.json()['detail']


async def test_only_a_place_has_backgrounds_by_time(client: AsyncClient, me: dict, more: dict, guard: dict):
    face, night = await pictured.upload(client, me), await pictured.upload(client, me)
    scenario = await pictured.draft(client, me, more, [timed(guard, face, night=night)], default_npc_sheet=SHEET)

    response = await happenings.publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['picture_time_not_place']


async def test_a_background_by_time_in_use_cannot_be_deleted(client: AsyncClient, me: dict, more: dict):
    day, night = await pictured.upload(client, me), await pictured.upload(client, me)
    await pictured.draft(client, me, more, [timed(more['gate'], day, night=night)])

    refused = await client.delete(f'{pictured.PORTRAITS_URL}/{night}', headers=me)

    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['code'] == 'portrait_in_use'


# --- 테이블 ---


async def test_the_map_shows_the_background_of_the_time_now(
    client: AsyncClient, me: dict, friend: dict, more: dict, guard: dict
):
    day, morning, square, night = [await pictured.upload(client, me) for _ in range(4)]
    # 판의 시계는 아침에 시작한다. 성문에는 아침의 그림이, 광장에는 밤의 그림만 있다
    pictures = [timed(more['gate'], day, morning=morning), timed(more['square'], square, night=night)]
    table = await pictured.start(client, me, friend, more, guard, pictures)

    seen = await read_table(client, friend, table)
    image = await client.get(table_url(table, f'/portraits/{night}/image'), headers=friend)

    assert seen['clock']['time_of_day'] == 'morning'
    assert pictured.place_pictures(seen)['성문'] == morning
    assert pictured.place_pictures(seen)['광장'] == square
    # 지금 때의 그림이 아니어도 그 판의 그림이라 받는다(시계가 흐르면 그림 창이 바꾼다)
    assert image.status_code == status.HTTP_200_OK


# --- 작은 함수들 ---

GATE = uuid.UUID('00000000-0000-4000-8000-0000000000a1')
SQUARE = uuid.UUID('00000000-0000-4000-8000-0000000000a3')
DAY = uuid.UUID('00000000-0000-4000-8000-0000000000b1')
NIGHT = uuid.UUID('00000000-0000-4000-8000-0000000000b3')
CONTENT = {
    'pictures': [
        {'entry_id': str(GATE), 'image_id': str(DAY), 'by_time': {'night': str(NIGHT)}},
        {'entry_id': str(SQUARE), 'image_id': str(DAY)},
    ]
}


def test_the_time_picks_the_background():
    assert place_picture(CONTENT, GATE, 'night') == NIGHT
    assert place_picture(CONTENT, GATE, 'morning') == DAY
    # 시계가 없는 테이블은 기본 그림이다
    assert place_picture(CONTENT, GATE, None) == DAY
    assert place_picture(CONTENT, SQUARE, 'night') == DAY
    assert place_picture(CONTENT, uuid.uuid4(), 'night') is None


def test_the_table_serves_the_backgrounds_by_time():
    assert timed_pictures(CONTENT) == {GATE: {'night': NIGHT}}
    assert table_portraits(CONTENT) == {DAY, NIGHT}
