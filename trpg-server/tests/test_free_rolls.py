# trpg-server/tests/test_free_rolls.py

"""
자유 굴림(#404)을 검증한다.

보는 것은 넷이다.
  - 주사위 설명을 정해진 모양으로만 읽는다(개수 상한, 면 수 허용 목록, 보정 상한). 다시 쓴 설명은 하나다.
  - 앉은 사람만, 끝나지 않은 테이블에서 굴린다. 눈은 서버의 주사위다. 같은 눈이면 같은 결과다.
  - 굴린 것이 이벤트(dice_rolled)로 모두에게 간다. 게임의 상태와 무관해 라운드를 되돌리는 것을 막지 않는다.
  - 한 사람이 굴리는 수를 센다.
"""

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient

from app.engine import dice_notation
from app.engine.dice import ScriptedDice
from app.engine.dice_notation import Notation, NotationError
from app.events.models import EventType
from app.limits.setup import build_limiting
from app.rounds.reverting import AFTER_OPENED
from tests import test_whispers as seats
from tests.conftest import make_test_settings

pytestmark = pytest.mark.usefixtures('clean_tables')

me = seats.me
friend = seats.friend
stranger = seats.stranger


# --- 주사위 설명 ---


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('d20', Notation(1, 20, 0)),
        ('2d6+1', Notation(2, 6, 1)),
        (' 3D8-2 ', Notation(3, 8, -2)),
        ('1d100', Notation(1, 100, 0)),
        ('10d4+100', Notation(10, 4, 100)),
    ],
)
def test_a_notation_reads_as_count_sides_and_bonus(text: str, expected: Notation):
    assert dice_notation.parse(text) == expected


@pytest.mark.parametrize(
    ('text', 'reason'),
    [
        ('', 'format'),
        ('20', 'format'),
        ('2d6+1d4', 'format'),
        ('d 20', 'format'),
        ('4d6kh3', 'format'),
        ('d20' + ' ' * 20 + '+1', 'format'),
        ('0d6', 'count'),
        ('11d6', 'count'),
        ('d7', 'sides'),
        ('d1000', 'format'),
        ('2d6+101', 'bonus'),
    ],
)
def test_a_notation_outside_the_shape_is_refused_with_its_reason(text: str, reason: str):
    with pytest.raises(NotationError) as refused:
        dice_notation.parse(text)

    assert refused.value.reason == reason


def test_the_notation_is_rewritten_one_way():
    assert [dice_notation.parse(text).text for text in ('1d20', 'D20+0', '2d6+01', '3d8-2')] == [
        'd20',
        'd20',
        '2d6+1',
        '3d8-2',
    ]


def test_the_same_faces_give_the_same_roll():
    rolled = dice_notation.roll(Notation(2, 6, 1), ScriptedDice([3, 4]))

    assert (rolled.faces, rolled.total) == ((3, 4), 8)


# --- API ---


async def seated(client: AsyncClient, me: dict, friend: dict) -> dict:
    """둘이 앉아 시작한 테이블."""
    table = await seats.open_trio(client, me, friend)
    await seats.start(client, table, {seats.ME: me, seats.FRIEND: friend})
    return table


async def roll(client: AsyncClient, headers: dict, table: dict, dice: str):
    return await client.post(seats.table_url(table, '/dice'), json={'dice': dice}, headers=headers)


async def test_a_seated_person_rolls_and_everyone_sees_it(client: AsyncClient, app: FastAPI, me: dict, friend: dict):
    table = await seated(client, me, friend)
    app.state.dice = ScriptedDice([3, 4])

    response = await roll(client, me, table, '2D6+1')

    assert response.status_code == status.HTTP_201_CREATED, response.text
    body = response.json()
    expected = {
        'user_id': str(seats.ME),
        'character_name': '엘프',
        'dice': '2d6+1',
        'faces': [3, 4],
        'bonus': 1,
        'total': 8,
    }
    assert {key: value for key, value in body.items() if key != 'sequence'} == expected
    (seen,) = await seats.events_of(client, friend, table, 'dice_rolled')
    assert (seen['sequence'], seen['payload']) == (body['sequence'], expected)


async def test_a_roll_before_the_start_is_fine_but_not_on_an_ended_table(client: AsyncClient, me: dict, friend: dict):
    table = await seats.open_trio(client, me, friend)

    before = await roll(client, friend, table, 'd20')
    await client.post(seats.table_url(table, '/end'), headers=me)
    after = await roll(client, friend, table, 'd20')

    assert (before.status_code, after.status_code) == (status.HTTP_201_CREATED, status.HTTP_409_CONFLICT)


async def test_those_not_seated_cannot_roll(client: AsyncClient, me: dict, friend: dict, stranger: dict):
    table = await seated(client, me, friend)

    response = await roll(client, stranger, table, 'd20')

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize('dice', ['d7', '11d6', '2d6+1d4', 'x' * 17])
async def test_a_notation_outside_the_shape_is_refused(client: AsyncClient, me: dict, friend: dict, dice: str):
    table = await seated(client, me, friend)

    response = await roll(client, me, table, dice)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert await seats.events_of(client, me, table, 'dice_rolled') == []


async def test_the_rolls_are_counted_per_person(client: AsyncClient, app: FastAPI, me: dict, friend: dict):
    table = await seated(client, me, friend)
    app.state.limiting = build_limiting(make_test_settings(limits_enabled=True, free_rolls_per_window=2), None)

    mine = [(await roll(client, me, table, 'd20')).status_code for _ in range(3)]
    theirs = (await roll(client, friend, table, 'd20')).status_code

    assert mine == [status.HTTP_201_CREATED, status.HTTP_201_CREATED, status.HTTP_429_TOO_MANY_REQUESTS]
    assert theirs == status.HTTP_201_CREATED


def test_a_roll_does_not_stop_reverting_a_round():
    assert EventType.DICE_ROLLED in AFTER_OPENED
