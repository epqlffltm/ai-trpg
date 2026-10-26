# trpg-server/tests/test_full_game.py

"""
한 판을 처음부터 끝까지 API 로 돈다(#810). 기능별 시험이 따로 보는 일들을 이어서, 라운드 안의 처리 순서가
어긋나는 회귀를 잡는다.

시나리오 → 테이블 → 캐릭터 → 선언 → 판정 → 서술 → 다음 라운드 → 끝냄을 셋이 돈다.
  - 서술자는 정해진 글을 내는 가짜다(tests/test_round_closing.py 의 GatedNarrator, 문을 열어 둔다).
    실제 모델은 부르지 않는다.
  - 결제 서버는 가짜다(tests/billing.py). 게임 서버의 시험은 결제 서버 없이 돈다. 결제 서버의 규칙(같은 이름표의 홀드,
    확정과 반환)은 가짜가 흉내 내고, 그 구현이 결제 서버와 같은지는 결제 서버의 시험이 본다.
  - 주사위는 정해진 눈을 낸다. 모두 근력·보통(15)의 판정을 낸다. 시트의 근력은 10(보정 0)이라 15 는 성공이다.
  - DB 는 실제 PostgreSQL 이다.

보는 것.
  - 한 라운드의 선언을 셋이 한꺼번에 내도 라운드는 한 번 닫히고, 서술자는 라운드마다 한 번 불린다.
  - 서술이 다음 라운드의 장면이 되고, 라운드의 번호가 하나씩 오른다. 각자의 판정은 그 라운드의 결과에 남는다.
  - 라운드마다 앉은 사람마다 홀드가 걸리고, 서술되면 한 번 확정된다. 끝낸 판의 열린 라운드의 홀드는 돌아온다.
  - 방장이 닫기를 한꺼번에 두 번 보내도 라운드는 한 번만 닫힌다.
"""

import asyncio
import uuid
from collections import Counter

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey

from tests.billing import PRICES, FakeBillingServer
from tests.narration_model import TEST_PRICE_CODE, with_model
from tests.sheets import SHEET
from tests.test_character_death import load_dice
from tests.test_narration_billing import tick
from tests.test_round_closing import (
    FRIEND,
    ME,
    OPENINGS,
    RESULT,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    TABLES_URL,
    GatedNarrator,
    bearer,
    current,
    table_url,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

THIRD = uuid.UUID('33333333-2222-4333-8444-555555555555')
PLAYERS = [ME, FRIEND, THIRD]
NAMES = {ME: '엘프', FRIEND: '영애', THIRD: '드워프'}
# 각자의 처음 크레딧. 이 파일의 판을 다 돌고도 남는다
CREDITS = 10_000
# 한 라운드의 서술 값(가짜 결제 서버의 테스트 모델 가격표)
PRICE = PRICES[TEST_PRICE_CODE]
# 근력·보통(15)의 판정. 성공하는 눈. 1 과 20(대실패, 대성공)은 쓰지 않는다. 다른 표를 굴리지 않게 한다
KICK = {'kind': 'check', 'ability': 'str', 'difficulty': 'medium'}
SUCCESS_ROLL = 15
# 서술이 끝날 때까지 돌 라운드의 수
ROUNDS = 3


@pytest.fixture
def players(signing_key: SigningKey) -> dict[uuid.UUID, dict[str, str]]:
    """셋의 머리말. 첫 사람(ME)이 방장이다."""
    return {user_id: bearer(signing_key, user_id) for user_id in PLAYERS}


@pytest.fixture
async def billing(app: FastAPI) -> FakeBillingServer:
    """앱에 꽂은 가짜 결제 서버. 셋 다 CREDITS 만큼 있다."""
    server = FakeBillingServer(balances=dict.fromkeys(PLAYERS, CREDITS))
    client = server.make_client()
    app.state.billing = server.billing(client)
    yield server
    await client.aclose()


@pytest.fixture
def narrator(app: FastAPI) -> GatedNarrator:
    """앱에 꽂은 서술자. 문을 열어 두어 불리면 바로 정해진 글(RESULT)을 낸다. 받은 것을 적어 둔다."""
    gated = GatedNarrator()
    gated.release()
    app.state.narrator = gated
    return gated


async def start_game(client: AsyncClient, players: dict[uuid.UUID, dict[str, str]]) -> dict:
    """시나리오를 만들어 게시하고, 셋이 앉아 캐릭터를 정하고, 방장이 시작한 테이블."""
    host = players[ME]
    rulebook = (await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=host)).json()
    body = {'title': '추격전', 'rulebook_id': rulebook['id'], 'openings': OPENINGS, 'default_sheet': SHEET}
    scenario = (await client.post(SCENARIOS_URL, json=with_model(body), headers=host)).json()
    published = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=host)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': len(PLAYERS)}
    table = (await client.post(TABLES_URL, json=body, headers=host)).json()
    for user_id in PLAYERS[1:]:
        joined = await client.post(
            f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=players[user_id]
        )
        assert joined.status_code == status.HTTP_200_OK, joined.text
    for user_id in PLAYERS:
        named = await client.put(
            table_url(table, '/character'), json={'name': NAMES[user_id]}, headers=players[user_id]
        )
        assert named.status_code == status.HTTP_200_OK, named.text
    started = await client.post(table_url(table, '/start'), headers=host)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table


async def declare_together(client: AsyncClient, players: dict[uuid.UUID, dict[str, str]], table: dict) -> list[int]:
    """셋이 한꺼번에 판정을 낸다. 응답의 상태 코드들을 돌려준다."""
    url = table_url(table, '/rounds/current/declaration')

    async def one(user_id: uuid.UUID) -> int:
        body = {'content': f'{NAMES[user_id]}이(가) 문을 걷어찬다.', 'action': KICK}
        return (await client.put(url, json=body, headers=players[user_id])).status_code

    return list(await asyncio.gather(*(one(user_id) for user_id in PLAYERS)))


async def round_of(client: AsyncClient, headers: dict[str, str], table: dict, number: int) -> dict:
    """그 번호의 라운드."""
    response = await client.get(table_url(table, f'/rounds/{number}'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def references_of(table: dict, number: int) -> set[str]:
    """그 라운드에 앉은 사람마다의 홀드의 이름표(app/billing/charges.py 의 reference_for)."""
    return {f'narration:{table["id"]}:{number}:{user_id}' for user_id in PLAYERS}


def captures(billing: FakeBillingServer) -> Counter[str]:
    """이름표마다 확정을 부른 횟수."""
    return Counter(reference for action, reference in billing.calls if action == 'capture')


async def test_three_play_a_whole_game_from_the_scenario_to_the_end(
    client: AsyncClient,
    app: FastAPI,
    players: dict[uuid.UUID, dict[str, str]],
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
):
    host = players[ME]
    table = await start_game(client, players)
    load_dice(app, [SUCCESS_ROLL] * len(PLAYERS) * ROUNDS)

    for number in range(1, ROUNDS + 1):
        # 열린 라운드의 홀드를 정리 작업이 건다
        await tick(app)
        codes = await declare_together(client, players, table)
        await narrated()
        # 서술이 확정되면 정리 작업이 결제 서버에 확정을 부른다
        await tick(app)

        assert codes == [status.HTTP_200_OK] * len(PLAYERS)
        closed = await round_of(client, host, table, number)
        assert closed['status'] == 'closed'
        assert sorted(declaration['outcome']['success'] for declaration in closed['declarations']) == [True] * 3
        opened = await current(client, host, table)
        assert (opened['number'], opened['status'], opened['scene']) == (number + 1, 'open', RESULT)

    # 서술자는 닫은 라운드마다 한 번 불렸다. 한꺼번에 낸 선언이 라운드를 두 번 닫지 않았다
    assert len(narrator.requests) == ROUNDS
    # 라운드마다 앉은 사람마다 홀드 하나, 확정 한 번
    statuses = billing.statuses()
    for number in range(1, ROUNDS + 1):
        assert {reference: statuses[reference] for reference in references_of(table, number)} == dict.fromkeys(
            references_of(table, number), 'captured'
        )
    assert set(captures(billing).values()) == {1}
    assert len(captures(billing)) == len(PLAYERS) * ROUNDS

    ended = await client.post(table_url(table, '/end'), headers=host)
    await tick(app)

    assert ended.status_code == status.HTTP_200_OK, ended.text
    # 끝낸 판의 열린 라운드(서술하지 않은 라운드)의 홀드는 돌아온다
    last = references_of(table, ROUNDS + 1)
    assert {reference: statuses for reference, statuses in billing.statuses().items() if reference in last} == (
        dict.fromkeys(last, 'released')
    )
    # 각자 서술된 라운드의 값만 냈다
    assert [billing.balance(user_id) for user_id in PLAYERS] == [CREDITS - PRICE * ROUNDS] * len(PLAYERS)


async def test_two_closes_at_once_close_the_round_once(
    client: AsyncClient,
    app: FastAPI,
    players: dict[uuid.UUID, dict[str, str]],
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
):
    host = players[ME]
    table = await start_game(client, players)
    narrator.hold()
    url = table_url(table, '/rounds/current/close')

    codes = await asyncio.gather(client.post(url, headers=host), client.post(url, headers=host))
    await narrator.wait_until_called()
    narrator.release()
    await narrated()
    await tick(app)

    # 하나는 닫고, 다른 하나는 이미 닫는 중이라 받지 않는다
    assert sorted(response.status_code for response in codes) == [status.HTTP_202_ACCEPTED, status.HTTP_409_CONFLICT]
    assert len(narrator.requests) == 1
    assert (await current(client, host, table))['number'] == 2
    assert (await round_of(client, host, table, 1))['status'] == 'closed'
    # 확정도 사람마다 한 번이다
    assert captures(billing) == Counter(dict.fromkeys(references_of(table, 1), 1))
