# trpg-server/tests/test_growth_raise.py

"""
쌓인 능력치 점수를 능력치에 놓는 것(#286 ③, app/tables/raising.py, app/tables/growth.py 의 raise_abilities)을 검증한다.

맵과 픽스처는 tests/test_growth.py 의 것이다. 룰북은 srd5 에 레벨표(GROWTH)를 적은 것이다. 최대 HP 에 닿는 능력치는
건강(con), 점수의 상한은 20, 보정은 (점수 - 10) // 2 다. 시트는 능력치가 모두 10, 최대 HP 10 이다.
왕녀 구출이 경험치 700 을 주면 레벨 4 가 되어 점수 4(1 + 1 + 2)를 받고 최대 HP 가 19 다.

보는 것.
  - 놓기: 고른 능력치가 그만큼 오르고 점수가 준다. 건강의 보정이 오르면 최대 HP 와 지금 HP 가 오른다.
    이벤트 abilities_raised(행한 사람은 그 사람). 테이블의 시트에 보인다.
  - 막기: 점수가 모자라면 409 not_enough_points, 상한을 넘으면 409 ability_at_max, 규칙에 없는 능력치면 422,
    0 이나 빈 요청은 422. 죽은 캐릭터는 409 character_dead, 라운드가 닫는 중이면 409 round_closing.
    막히면 아무것도 바뀌지 않는다.
  - 순수 함수: 쓰러진 캐릭터는 최대 HP 만 오른다. 보정이 그대로면 최대 HP 도 그대로다.
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.templates import Template, from_template
from app.tables import growth
from app.tables.errors import TableConflictError, TableOptionError
from app.tables.models import TableSheet
from app.transcripts.markdown import render_event
from tests import test_growth as growth_tests
from tests.test_clock_narration import held_jobs  # noqa: F401 (테스트가 픽스처로 쓴다)
from tests.test_growth import sheet_of, start_growing
from tests.test_map_actions import going, play
from tests.test_table_items import FRIEND, ME, events_of, kill, read_table, table_url
from tests.test_transcript_markdown import LABELS, event

pytestmark = pytest.mark.usefixtures('clean_tables')

me = growth_tests.me
friend = growth_tests.friend
lore = growth_tests.lore
more = growth_tests.more


async def grown(client: AsyncClient, me: dict, friend: dict, more: dict, narrated) -> dict:
    """레벨 4 가 되어 점수 4 를 쌓은 테이블. 광장에 닿아 왕녀 구출을 이뤘다."""
    table = await start_growing(client, me, friend, more, 700)
    await play(client, me, friend, table, narrated, mine=going(more['square']))
    return table


async def spend(client: AsyncClient, headers: dict, table: dict, **raises: int):
    return await client.post(table_url(table, '/abilities'), json={'raises': raises}, headers=headers)


# --- 놓기 ---


async def test_points_raise_the_chosen_abilities(client: AsyncClient, me: dict, friend: dict, more: dict, narrated):
    table = await grown(client, me, friend, more, narrated)

    response = await spend(client, me, table, con=2, str=1)

    assert response.status_code == status.HTTP_200_OK, response.text
    sheet = sheet_of(response.json(), ME)
    assert (sheet['abilities']['con'], sheet['abilities']['str'], sheet['points']) == (12, 11, 1)
    # 건강 10 → 12 로 보정이 0 → 1 이 되어 최대 HP 와 지금 HP 가 1 오른다
    assert (sheet['max_hp'], sheet['hp']) == (20, 20)
    (raised,) = await events_of(client, me, table, 'abilities_raised')
    assert raised['actor_id'] == str(ME)
    assert raised['payload'] == {
        'user_id': str(ME),
        'character_name': '기사',
        'raises': [
            {'ability': 'str', 'name': '근력', 'from': 10, 'to': 11},
            {'ability': 'con', 'name': '건강', 'from': 10, 'to': 12},
        ],
        'points': 1,
        'max_hp': 20,
    }
    # 다른 사람의 시트는 그대로다
    assert sheet_of(await read_table(client, friend, table), FRIEND)['points'] == 4


async def test_the_points_are_spent_once(client: AsyncClient, me: dict, friend: dict, more: dict, narrated):
    table = await grown(client, me, friend, more, narrated)

    first = await spend(client, me, table, dex=4)
    second = await spend(client, me, table, dex=1)

    assert first.status_code == status.HTTP_200_OK
    assert (second.status_code, second.json()['reason']) == (status.HTTP_409_CONFLICT, 'not_enough_points')
    assert sheet_of(await read_table(client, me, table), ME)['abilities']['dex'] == 14


# --- 막기 ---


@pytest.mark.parametrize(
    ('raises', 'code', 'reason'),
    [
        ({'con': 5}, status.HTTP_409_CONFLICT, 'not_enough_points'),
        ({'con': 2, 'str': 3}, status.HTTP_409_CONFLICT, 'not_enough_points'),
        ({'luck': 1}, status.HTTP_422_UNPROCESSABLE_CONTENT, None),
        ({'con': 0}, status.HTTP_422_UNPROCESSABLE_CONTENT, None),
        ({}, status.HTTP_422_UNPROCESSABLE_CONTENT, None),
    ],
    ids=['too-many', 'too-many-together', 'unknown', 'zero', 'empty'],
)
async def test_a_wrong_spend_changes_nothing(
    client: AsyncClient, me: dict, friend: dict, more: dict, narrated, raises: dict, code: int, reason: str | None
):
    table = await grown(client, me, friend, more, narrated)

    response = await spend(client, me, table, **raises)

    assert response.status_code == code, response.text
    if reason is not None:
        assert response.json()['reason'] == reason
    sheet = sheet_of(await read_table(client, me, table), ME)
    assert (sheet['points'], sheet['abilities']['con'], sheet['max_hp']) == (4, 10, 19)
    assert await events_of(client, me, table, 'abilities_raised') == []


async def test_an_ability_does_not_pass_the_cap(
    client: AsyncClient, me: dict, friend: dict, more: dict, session: AsyncSession, narrated
):
    table = await grown(client, me, friend, more, narrated)
    await session.execute(
        text('UPDATE table_sheets SET abilities = abilities || \'{"str": 19}\' WHERE user_id = :user_id'),
        {'user_id': ME},
    )
    await session.commit()

    over = await spend(client, me, table, str=2)
    up_to = await spend(client, me, table, str=1)

    assert (over.status_code, over.json()['reason']) == (status.HTTP_409_CONFLICT, 'ability_at_max')
    assert up_to.status_code == status.HTTP_200_OK
    assert sheet_of(up_to.json(), ME)['abilities']['str'] == 20


async def test_the_dead_spend_nothing(
    client: AsyncClient, me: dict, friend: dict, more: dict, session: AsyncSession, narrated
):
    table = await grown(client, me, friend, more, narrated)
    await kill(session, FRIEND)
    await session.commit()

    response = await spend(client, friend, table, con=1)

    assert (response.status_code, response.json()['reason']) == (status.HTTP_409_CONFLICT, 'character_dead')


async def test_nothing_is_spent_while_the_round_closes(
    client: AsyncClient,
    me: dict,
    friend: dict,
    more: dict,
    held_jobs,  # noqa: F811
):
    table = await start_growing(client, me, friend, more, 700)
    # 둘 다 내면 닫기 시작한다. 서술은 돌지 않아 닫는 중에 머문다. 점수는 닫기를 시작할 때 받았다
    for headers, action in ((me, going(more['square'])), (friend, None)):
        body = {'content': '간다.', **({'action': action} if action else {})}
        await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=headers)

    response = await spend(client, me, table, con=1)

    assert (response.status_code, response.json()['reason']) == (status.HTTP_409_CONFLICT, 'round_closing')


def test_the_transcript_names_the_raise():
    payload = {'character_name': '기사', 'raises': [{'name': '근력', 'from': 12, 'to': 13}], 'points': 0}

    assert '능력치: 기사 · 근력 12 → 13' in render_event(event('abilities_raised', payload), LABELS)


# --- 순수 함수 ---

SRD5 = from_template(Template.SRD5)


def sheet(con: int = 10, hp: int = 10, max_hp: int = 10, points: int = 3) -> TableSheet:
    scores = {ability.key: 10 for ability in SRD5.abilities}
    return TableSheet(abilities={**scores, 'con': con}, hp=hp, max_hp=max_hp, points=points)


def test_a_downed_character_gains_only_the_maximum():
    downed = sheet(hp=0)

    growth.raise_abilities(SRD5, downed, {'con': 2})

    assert (downed.hp, downed.max_hp, downed.points) == (0, 11, 1)


def test_the_maximum_follows_the_modifier_not_the_score():
    odd = sheet(con=11)
    plain = sheet()

    growth.raise_abilities(SRD5, odd, {'con': 1})
    growth.raise_abilities(SRD5, plain, {'con': 1})

    # 11 → 12 는 보정이 0 → 1, 10 → 11 은 그대로 0 이다
    assert (odd.max_hp, plain.max_hp) == (11, 10)


def test_a_refused_raise_leaves_the_sheet():
    full = sheet(points=1)
    before = (dict(full.abilities), full.points, full.max_hp)

    for raises, error in (({'con': 2}, TableConflictError), ({'luck': 1}, TableOptionError)):
        with pytest.raises(error):
            growth.raise_abilities(SRD5, full, raises)

    assert (full.abilities, full.points, full.max_hp) == before
