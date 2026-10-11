# game-server/tests/test_round_closing.py

"""
라운드를 닫는 과정을 검증한다. 닫기 시작 → GM 의 서술(뒤에서 돈다) → 닫기 마무리.

서술자가 답하는 때를 테스트가 정한다(GatedNarrator). "서술하는 동안"을 붙잡아 두고 그사이를 본다.

보는 것은 여섯이다.
  - 서술하는 동안 테이블이 멈추지 않는다. 채팅, 읽기, 나가기가 된다.
  - 서술자는 닫힐 때의 모습을 받는다. 그 뒤에 누가 나가도, 방장이 문체를 바꿔도, 서술을 다시 맡겨도 같다.
  - 닫는 중인 라운드에는 선언을 낼 수 없고, 또 닫을 수 없다. 서술자는 한 번만 불린다.
  - 서술이 끝내 실패하면 라운드가 닫는 중에 머물고, 모두에게 알린다. 방장은 기다리지 않고 다시 맡길 수 있다.
  - 같은 라운드의 서술이 둘 돌아도 다음 라운드는 하나만 열린다.
  - 서술하는 사이에 테이블이 끝나면 다음 라운드를 열지 않는다.

서술을 맡은 작업(app/rounds/closing.py)이 어디서 실패하든 끝나는지도 본다. 이때는 맡긴 작업을 돌리지 않고
버린 뒤(held) 테스트가 작업을 직접 돌린다. 실패를 끼워 넣고, 짧은 시간을 꽂고, 옛 작업을 흉내 낸다.
  - 고르기가 실패하거나 멈춰도 서술은 한다. 읽기, 서술, 마무리가 실패하면 실패를 적는다.
  - 시간이 다 되면 끊고 실패를 적는다. 실패를 적는 것이 멈춰도 작업은 끝난다.
  - 다시 맡긴 뒤의 옛 작업은 라운드를 읽지도, 닫지도, 실패를 적지도 못한다.
"""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import ProviderError
from app.main import API_PREFIX
from app.realtime.service import Cursor
from app.rounds import closing, service
from app.rounds.closing import Budgets, failure_reason, seconds_left
from app.rounds.llm_narrator import NarrationError
from app.rounds.models import Round
from app.rounds.narration_request import dump_moves
from app.rounds.narrator import NO_PREVIEW, FakeNarrator, NarrationRequest, Preview
from app.rounds.retrying_narrator import NarrationFailed
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')

# 테스트에 쓰는 예시. 내용은 아무 뜻이 없다
OPENINGS = ['사이렌이 울린다. 망치를 든 드워프가 쫓아온다.']
MY_ACTION = '바이크에 시동을 건다.'
FRIENDS_ACTION = '드워프에게 손을 흔든다.'
RESULT = '드워프가 넘어졌다.'

# 서술자가 불리기를 기다리는 가장 긴 시간(초)
SOON = 2.0


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 테이블을 여는 방장이다. 캐릭터는 '엘프'다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 들어오는 사람의 머리말. 캐릭터는 '영애'다."""
    return bearer(signing_key, FRIEND)


class GatedNarrator:
    """
    문 앞에서 기다리는 서술자. 테스트가 문을 열어 줘야(release) 답한다.

    불릴 때마다 받은 것을 적어 둔다. fail_next 를 켜 두면 다음 한 번은 답하는 대신 실패한다.
    """

    def __init__(self) -> None:
        self.requests: list[NarrationRequest] = []
        self.fail_next = False
        self._called = asyncio.Event()
        self._gate = asyncio.Event()

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        self.requests.append(request)
        self._called.set()
        await self._gate.wait()
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError('서술자가 답하지 못했다')
        return RESULT

    async def wait_until_called(self, times: int = 1) -> None:
        """서술자가 times 번 불릴 때까지 기다린다. 서술이 돌기 시작했다는 뜻이다."""
        async with asyncio.timeout(SOON):
            while len(self.requests) < times:
                self._called.clear()
                await self._called.wait()

    def release(self) -> None:
        """문을 연다. 기다리던 서술과 그 뒤의 서술이 모두 바로 답한다."""
        self._gate.set()

    def hold(self) -> None:
        """문을 다시 닫는다."""
        self._gate.clear()


class FailingNarrator:
    """늘 정해 둔 예외를 내는 서술자."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        raise self.error


@pytest.fixture
def narrator(app: FastAPI) -> GatedNarrator:
    """앱에 꽂은 문 앞의 서술자. 테스트가 끝날 때 문을 열어 둔다. 기다리던 작업이 남지 않게 한다."""
    gated = GatedNarrator()
    app.state.narrator = gated
    yield gated
    gated.release()


def table_url(table: dict, path: str = '') -> str:
    """테이블의 주소."""
    return f'{TABLES_URL}/{table["id"]}{path}'


async def start_duo(client: AsyncClient, me: dict[str, str], friend: dict[str, str]) -> dict:
    """나와 친구가 앉은 테이블을 시작한다. 이벤트가 다섯 개 적혀 있다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=me)
    body = {'title': '추격전', 'rulebook_id': rulebook.json()['id'], 'openings': OPENINGS, 'default_sheet': SHEET}
    scenario = (await client.post(SCENARIOS_URL, json=body, headers=me)).json()
    await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2}
    table = (await client.post(TABLES_URL, json=body, headers=me)).json()
    await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    await client.put(table_url(table, '/character'), json={'name': '영애'}, headers=friend)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table


async def declare(client: AsyncClient, headers: dict[str, str], table: dict, content: str) -> dict:
    """선언을 내고, 돌아온 라운드를 돌려준다."""
    url = table_url(table, '/rounds/current/declaration')
    response = await client.put(url, json={'content': content}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def begin_closing(client: AsyncClient, me: dict, friend: dict, table: dict, narrator: GatedNarrator) -> None:
    """둘 다 선언을 내서 라운드를 닫기 시작하게 한다. 서술이 돌기 시작할 때까지 기다린다."""
    await declare(client, me, table, MY_ACTION)
    await declare(client, friend, table, FRIENDS_ACTION)
    await narrator.wait_until_called()


async def current(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    """가장 최근 라운드를 읽는다."""
    response = await client.get(table_url(table, '/rounds/current'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def last_event(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    """테이블의 마지막 이벤트."""
    response = await client.get(table_url(table, '/events'), params={'after': 5}, headers=headers)
    return response.json()['items'][-1]


async def event_types(client: AsyncClient, headers: dict[str, str], table: dict, after: int = 5) -> list[str]:
    """테이블의 이벤트 종류를 순서대로. 시작할 때까지의 다섯은 건너뛴다."""
    response = await client.get(table_url(table, '/events'), params={'after': after}, headers=headers)
    return [event['type'] for event in response.json()['items']]


# --- 서술하는 동안 ---


async def test_the_table_keeps_working_while_the_gm_narrates(
    client: AsyncClient, me: dict, friend: dict, narrator: GatedNarrator, narrated
):
    table = await start_duo(client, me, friend)
    await begin_closing(client, me, friend, table, narrator)

    # 서술자는 아직 답하지 않았다. 그사이에 채팅을 쓰고, 읽고, 테이블을 본다
    chat = await client.post(table_url(table, '/messages'), json={'content': '어떻게 될까?'}, headers=friend)
    round_ = await current(client, me, table)
    seen = await client.get(table_url(table), headers=friend)

    # 테이블을 잠근 채로 서술을 기다렸다면 채팅이 여기서 멈춘다
    assert chat.status_code == status.HTTP_201_CREATED
    assert seen.status_code == status.HTTP_200_OK
    assert (round_['number'], round_['status'], round_['closed_at']) == (1, 'closing', None)

    narrator.release()
    await narrated()

    second = await current(client, me, table)
    assert (second['number'], second['status'], second['scene']) == (2, 'open', RESULT)


async def test_declarations_are_shown_to_everyone_once_the_round_is_closing(
    client: AsyncClient, me: dict, friend: dict, narrator: GatedNarrator
):
    table = await start_duo(client, me, friend)
    await begin_closing(client, me, friend, table, narrator)

    round_ = await current(client, friend, table)

    # 선언을 마감했다. 더 바뀌지 않으므로 가릴 이유가 없다. 이벤트 기록에도 이미 적혀 있다
    shown = {declaration['character_name']: declaration['content'] for declaration in round_['declarations']}
    assert shown == {'엘프': MY_ACTION, '영애': FRIENDS_ACTION}
    assert round_['waiting_for'] == []
    assert await event_types(client, friend, table) == ['player_action', 'player_action', 'round_closed']


async def test_the_closing_is_announced_before_the_narration_arrives(
    client: AsyncClient, me: dict, friend: dict, narrator: GatedNarrator, connect
):
    table = await start_duo(client, me, friend)
    reader = connect(table, FRIEND, Cursor(events=5))
    await reader.settle()

    await begin_closing(client, me, friend, table, narrator)

    # 닫기 시작한 것이 먼저 온다. 화면은 "GM 이 서술하는 중"을 띄울 수 있다
    closing = await reader.take(3)
    assert [json.loads(frame.data)['type'] for frame in closing] == ['player_action', 'player_action', 'round_closed']
    assert await reader.is_quiet()

    narrator.release()

    # 서술이 끝나면 나머지가 온다
    rest = await reader.take(2)
    assert [json.loads(frame.data)['type'] for frame in rest] == ['gm_narration', 'round_opened']
    assert json.loads(rest[0].data)['payload'] == {'text': RESULT}


async def test_someone_can_leave_while_the_gm_narrates(
    client: AsyncClient, me: dict, friend: dict, narrator: GatedNarrator, narrated
):
    table = await start_duo(client, me, friend)
    await begin_closing(client, me, friend, table, narrator)

    left = await client.delete(table_url(table, '/members/me'), headers=friend)
    narrator.release()
    await narrated()

    assert left.status_code == status.HTTP_204_NO_CONTENT
    # 서술은 끝까지 가고 다음 라운드가 열린다. 남은 사람만 기다린다
    second = await current(client, me, table)
    assert (second['number'], second['waiting_for']) == (2, [str(ME)])


async def test_the_gm_hears_the_round_as_it_closed_even_after_someone_leaves(
    client: AsyncClient, me: dict, friend: dict, narrator: GatedNarrator, narrated, monkeypatch: pytest.MonkeyPatch
):
    table = await start_duo(client, me, friend)
    narrator.fail_next = True
    narrator.release()
    await declare(client, me, table, MY_ACTION)
    await declare(client, friend, table, FRIENDS_ACTION)
    await narrated()

    # 첫 서술은 실패했다. 다시 맡기기 전에 친구가 나간다
    left = await client.delete(table_url(table, '/members/me'), headers=friend)
    monkeypatch.setattr(service, 'CLOSING_RETRY_SECONDS', 0)
    again = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()

    assert left.status_code == status.HTTP_204_NO_CONTENT
    assert again.status_code == status.HTTP_202_ACCEPTED
    # 친구의 행동은 기록에 있다. 지금 앉은 사람으로 다시 만들면 장면에서만 빠진다.
    # 서술자는 닫힐 때 굳혀 둔 것을 받는다. 처음 받은 것과 같다
    first, second = narrator.requests
    assert second == first
    assert [(move.character_name, move.content) for move in second.moves] == [
        ('엘프', MY_ACTION),
        ('영애', FRIENDS_ACTION),
    ]


async def test_the_gm_is_not_told_later_what_someone_who_left_before_closing_declared(
    client: AsyncClient, me: dict, friend: dict, narrator: GatedNarrator, narrated
):
    table = await start_duo(client, me, friend)
    narrator.release()
    # 친구는 선언을 내고 마감 전에 나간다. 그 선언은 판정도 서술도 받지 않는다
    await declare(client, friend, table, FRIENDS_ACTION)
    await client.delete(table_url(table, '/members/me'), headers=friend)
    await declare(client, me, table, MY_ACTION)
    await narrated()
    await declare(client, me, table, MY_ACTION)
    await narrated()

    first, second = narrator.requests
    assert [move.character_name for move in first.moves] == ['엘프']
    # 2 라운드의 서술자가 받는 지난 기록에도 없다. 1 라운드의 서술자가 받은 것과 같다
    assert [past.lines for past in second.history] == [[f'엘프: {MY_ACTION}']]
    # 선언 자체는 라운드의 기록에 남는다
    kept = (await client.get(table_url(table, '/rounds/1'), headers=me)).json()
    assert {item['character_name'] for item in kept['declarations']} == {'엘프', '영애'}


async def test_the_gm_is_still_told_later_what_someone_who_left_after_closing_declared(
    client: AsyncClient, me: dict, friend: dict, narrator: GatedNarrator, narrated
):
    table = await start_duo(client, me, friend)
    await begin_closing(client, me, friend, table, narrator)
    # 마감한 뒤에 나간다. 친구의 행동은 1 라운드의 서술에 들어갔다
    await client.delete(table_url(table, '/members/me'), headers=friend)
    narrator.release()
    await narrated()
    await declare(client, me, table, MY_ACTION)
    await narrated()

    # 지금 앉은 사람으로 지난 일을 거르지 않는다
    assert narrator.requests[-1].history[0].lines == [f'엘프: {MY_ACTION}', f'영애: {FRIENDS_ACTION}']


async def test_the_moves_are_kept_on_the_round_when_it_starts_closing(
    client: AsyncClient, me: dict, friend: dict, narrator: GatedNarrator, session: AsyncSession
):
    table = await start_duo(client, me, friend)
    await begin_closing(client, me, friend, table, narrator)

    kept = await session.scalar(select(Round.moves).where(Round.table_id == uuid.UUID(table['id'])))

    # 서술자가 받은 것이 라운드에 굳혀 있는 그것이다
    (request,) = narrator.requests
    assert kept == dump_moves(request.moves)


async def test_a_round_that_began_closing_before_moves_were_kept_is_narrated_from_the_seats(
    client: AsyncClient,
    me: dict,
    friend: dict,
    narrator: GatedNarrator,
    narrated,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    table = await start_duo(client, me, friend)
    narrator.fail_next = True
    narrator.release()
    await declare(client, me, table, MY_ACTION)
    await declare(client, friend, table, FRIENDS_ACTION)
    await narrated()
    # 굳히기 전의 서버가 닫기 시작한 라운드인 것처럼 칸을 비운다
    query = update(Round).where(Round.table_id == uuid.UUID(table['id'])).values(moves=None, narration_style=None)
    await session.execute(query)
    await session.commit()

    monkeypatch.setattr(service, 'CLOSING_RETRY_SECONDS', 0)
    again = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()

    # 멈춘 채로 남지 않는다. 지금 앉은 사람들로 만들어 서술한다
    assert again.status_code == status.HTTP_202_ACCEPTED
    assert narrator.requests[1].moves == narrator.requests[0].moves
    # 문체도 지금 테이블의 것이다
    assert narrator.requests[1].style == narrator.requests[0].style == 'classic'
    assert (await current(client, me, table))['number'] == 2


async def test_a_new_style_starts_from_the_next_narration(
    client: AsyncClient, me: dict, friend: dict, narrator: GatedNarrator, narrated
):
    table = await start_duo(client, me, friend)
    await begin_closing(client, me, friend, table, narrator)

    # 서술이 도는 사이에 방장이 문체를 바꾼다
    changed = await client.put(table_url(table, '/narration-style'), json={'narration_style': 'dopamine'}, headers=me)
    narrator.release()
    await narrated()
    narrator.hold()
    await declare(client, me, table, MY_ACTION)
    await declare(client, friend, table, FRIENDS_ACTION)
    await narrator.wait_until_called(times=2)

    assert changed.status_code == status.HTTP_200_OK
    # 돌고 있던 서술은 닫기 시작할 때의 문체 그대로다. 바꾼 문체는 다음 라운드의 서술부터다
    first, second = narrator.requests
    assert (first.style, second.style) == ('classic', 'dopamine')


async def test_handing_a_stalled_round_again_keeps_its_style(
    client: AsyncClient, me: dict, friend: dict, narrator: GatedNarrator, narrated, monkeypatch: pytest.MonkeyPatch
):
    table = await start_duo(client, me, friend)
    narrator.fail_next = True
    narrator.release()
    await declare(client, me, table, MY_ACTION)
    await declare(client, friend, table, FRIENDS_ACTION)
    await narrated()

    # 첫 서술은 실패했다. 다시 맡기기 전에 방장이 문체를 바꾼다
    await client.put(table_url(table, '/narration-style'), json={'narration_style': 'literary'}, headers=me)
    monkeypatch.setattr(service, 'CLOSING_RETRY_SECONDS', 0)
    await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()

    # 다시 맡겨도 이 라운드는 닫기 시작할 때의 문체다. 서술을 실패시켜 문체를 바꿀 수 없다
    first, second = narrator.requests
    assert first.style == second.style == 'classic'


# --- 닫는 중인 라운드 ---


async def test_a_closing_round_takes_no_declarations(
    client: AsyncClient, me: dict, friend: dict, narrator: GatedNarrator
):
    table = await start_duo(client, me, friend)
    await begin_closing(client, me, friend, table, narrator)

    url = table_url(table, '/rounds/current/declaration')
    response = await client.put(url, json={'content': '마음을 바꿨다.'}, headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'round_closing'
    # 마감한 선언은 그대로다
    round_ = await current(client, me, table)
    assert MY_ACTION in [declaration['content'] for declaration in round_['declarations']]


async def test_closing_again_while_the_gm_narrates_is_refused(
    client: AsyncClient, me: dict, friend: dict, narrator: GatedNarrator, narrated
):
    table = await start_duo(client, me, friend)
    await begin_closing(client, me, friend, table, narrator)

    again = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    narrator.release()
    await narrated()

    # 서술이 돌고 있다. 또 맡기면 같은 서술을 두 번 시키게 된다
    assert again.status_code == status.HTTP_409_CONFLICT
    assert again.json()['reason'] == 'round_closing'
    assert len(narrator.requests) == 1
    # 닫힘은 한 번만 적혔다
    assert (await event_types(client, me, table)).count('round_closed') == 1


# --- 서술이 실패하면 ---


async def test_a_failed_narration_leaves_the_round_closing_and_tells_everyone(
    client: AsyncClient, me: dict, friend: dict, narrator: GatedNarrator, narrated, caplog: pytest.LogCaptureFixture
):
    table = await start_duo(client, me, friend)
    narrator.fail_next = True
    narrator.release()

    with caplog.at_level(logging.ERROR, logger='app.core.jobs'):
        await declare(client, me, table, MY_ACTION)
        await declare(client, friend, table, FRIENDS_ACTION)
        await narrated()

    # 라운드는 닫는 중에 머문다. 다음 라운드가 열리지 않았다. 실패한 시각이 적혀 있다
    round_ = await current(client, me, table)
    assert (round_['number'], round_['status']) == (1, 'closing')
    assert round_['narration_failed_at'] is not None
    # 앉은 사람 모두가 실패를 안다. "GM 이 서술하는 중"에 머물지 않는다
    assert await event_types(client, friend, table) == [
        'player_action',
        'player_action',
        'round_closed',
        'narration_failed',
    ]
    # 버그로 실패하면 예외의 글을 내보내지 않는다. 자세한 것은 로그에 남는다
    assert (await last_event(client, friend, table))['payload'] == {'round': 1, 'reason': 'error'}
    (record,) = caplog.records
    assert f'narrate:{table["id"]}:1' in record.getMessage()
    # 채팅은 여전히 된다. 테이블이 통째로 멈춘 것이 아니다
    chat = await client.post(table_url(table, '/messages'), json={'content': '멈췄나?'}, headers=friend)
    assert chat.status_code == status.HTTP_201_CREATED


async def test_the_reason_of_the_failure_is_told(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated, caplog: pytest.LogCaptureFixture
):
    app.state.narrator = FailingNarrator(NarrationFailed('timeout'))
    table = await start_duo(client, me, friend)

    with caplog.at_level(logging.ERROR, logger='app.core.jobs'):
        await declare(client, me, table, MY_ACTION)
        await declare(client, friend, table, FRIENDS_ACTION)
        await narrated()

    # 다시 시도하고 넘어가도 안 됐다. 마지막 실패의 이유가 보인다
    assert (await last_event(client, friend, table))['payload'] == {'round': 1, 'reason': 'timeout'}


async def test_the_host_can_hand_a_failed_round_to_the_gm_again_at_once(
    client: AsyncClient, me: dict, friend: dict, narrator: GatedNarrator, narrated
):
    table = await start_duo(client, me, friend)
    narrator.fail_next = True
    narrator.release()
    await declare(client, me, table, MY_ACTION)
    await declare(client, friend, table, FRIENDS_ACTION)
    await narrated()

    # 실패한 것을 안다. 멈춘 지 한참 지나기를 기다리지 않는다. 방장만 다시 맡긴다
    by_member = await client.post(table_url(table, '/rounds/current/close'), headers=friend)
    by_host = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()

    assert by_member.status_code == status.HTTP_403_FORBIDDEN
    assert by_host.status_code == status.HTTP_202_ACCEPTED
    # 이번에는 서술이 끝나 다음 라운드가 열렸다
    second = await current(client, me, table)
    assert (second['number'], second['scene']) == (2, RESULT)
    # 다시 맡겨도 행동과 닫힘을 또 적지 않는다. 처음 닫을 때 적은 것에 실패, 서술, 열림이 이어진다
    assert await event_types(client, me, table) == [
        'player_action',
        'player_action',
        'round_closed',
        'narration_failed',
        'gm_narration',
        'round_opened',
    ]
    # 서술자는 처음에 받은 것과 같은 것을 다시 받았다
    assert narrator.requests[0] == narrator.requests[1]


async def test_handing_a_failed_round_again_clears_the_failure(
    client: AsyncClient, me: dict, friend: dict, narrator: GatedNarrator, narrated
):
    table = await start_duo(client, me, friend)
    narrator.fail_next = True
    narrator.release()
    await declare(client, me, table, MY_ACTION)
    await declare(client, friend, table, FRIENDS_ACTION)
    await narrated()
    narrator.hold()

    await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrator.wait_until_called(times=2)
    again = await client.post(table_url(table, '/rounds/current/close'), headers=me)

    # 다시 맡긴 서술이 돌고 있다. 실패의 표시가 지워져서, 또 맡기려면 다시 기다려야 한다
    assert (await current(client, me, table))['narration_failed_at'] is None
    assert again.status_code == status.HTTP_409_CONFLICT


async def test_a_failure_is_told_only_for_a_round_still_closing(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrator: GatedNarrator, narrated
):
    table = await start_duo(client, me, friend)
    narrator.release()
    await declare(client, me, table, MY_ACTION)
    await declare(client, friend, table, FRIENDS_ACTION)
    await narrated()

    # 같은 라운드의 다른 서술이 먼저 마무리했다. 늦게 실패한 쪽은 아무것도 적지 않는다
    async with app.state.session_factory() as session:
        await service.fail_closing(session, uuid.UUID(table['id']), 1, await started_at(app, table), 'timeout')

    assert 'narration_failed' not in await event_types(client, me, table)


async def test_a_failure_is_told_once(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrator: GatedNarrator, narrated
):
    table = await start_duo(client, me, friend)
    narrator.fail_next = True
    narrator.release()
    await declare(client, me, table, MY_ACTION)
    await declare(client, friend, table, FRIENDS_ACTION)
    await narrated()

    # 이미 실패가 적힌 라운드다. 또 적지 않는다
    async with app.state.session_factory() as session:
        await service.fail_closing(session, uuid.UUID(table['id']), 1, await started_at(app, table), 'timeout')

    assert (await event_types(client, me, table)).count('narration_failed') == 1


@pytest.mark.parametrize(
    ('error', 'reason'),
    [
        (NarrationFailed('cut_off'), 'cut_off'),
        (ProviderError('unreachable'), 'unreachable'),
        (NarrationError('empty'), 'empty'),
        (RuntimeError('DB 비밀번호가 틀렸다'), 'error'),
        # 작업 전체의 시간이 다 됐다
        (TimeoutError(), 'timeout'),
    ],
)
def test_the_reason_comes_from_the_narrator_failure(error: Exception, reason: str):
    # 서술자의 실패는 그 이유를 쓴다. 그 밖의 예외는 글을 내보내지 않는다
    assert failure_reason(error) == reason


async def test_two_narrations_of_one_round_open_only_one_next_round(
    client: AsyncClient,
    me: dict,
    friend: dict,
    narrator: GatedNarrator,
    narrated,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    table = await start_duo(client, me, friend)
    await begin_closing(client, me, friend, table, narrator)

    # 첫 서술이 아직 도는데 다시 맡긴다. 서술 둘이 같은 라운드를 두고 돈다
    monkeypatch.setattr(service, 'CLOSING_RETRY_SECONDS', 0)
    again = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrator.wait_until_called(times=2)
    with caplog.at_level(logging.ERROR, logger='app.core.jobs'):
        narrator.release()
        await narrated()

    assert again.status_code == status.HTTP_202_ACCEPTED
    assert len(narrator.requests) == 2
    # 다시 맡긴 쪽만 받아들여진다. 다음 라운드는 하나다
    rounds = (await client.get(table_url(table, '/rounds'), headers=me)).json()
    assert [(round_['number'], round_['status']) for round_ in rounds['items']] == [(1, 'closed'), (2, 'open')]
    assert (await event_types(client, me, table)).count('gm_narration') == 1
    # 앞서 맡은 쪽은 "내 차례가 아니네" 하고 조용히 물러난다. DB 의 유일 조건에 부딪혀 실패하는 것이 아니다
    assert caplog.records == []


# --- 서술을 맡은 작업이 어디서 실패하든 끝난다 ---


class HeldJobs:
    """맡은 작업을 돌리지 않고 버리는 것. 라운드를 닫는 중에 세워 두고 테스트가 작업을 직접 돌린다."""

    def __init__(self) -> None:
        self.names: list[str] = []

    def spawn(self, job, name: str) -> None:
        job.close()
        self.names.append(name)

    def count(self) -> int:
        return 0

    async def drain(self) -> None:
        return None

    async def aclose(self) -> None:
        return None


@pytest.fixture
def held(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> HeldJobs:
    """앱이 맡기는 작업을 돌리지 않게 한다."""
    jobs = HeldJobs()
    monkeypatch.setattr(app.state, 'jobs', jobs)
    return jobs


async def started_at(app: FastAPI, table: dict, number: int = 1) -> datetime:
    """라운드에 적힌 닫기 시작한 시각. 서술을 맡은 작업이 들고 다니는 값이다."""
    async with app.state.session_factory() as session:
        query = select(Round.closing_at).where(Round.table_id == uuid.UUID(table['id']), Round.number == number)
        return await session.scalar(query)


async def hold_closing(client: AsyncClient, app: FastAPI, me: dict, friend: dict) -> tuple[dict, datetime]:
    """둘 다 선언을 내서 닫는 중인 라운드를 만든다(held 와 함께 쓴다). 테이블과 닫기 시작한 시각을 돌려준다."""
    table = await start_duo(client, me, friend)
    await declare(client, me, table, MY_ACTION)
    await declare(client, friend, table, FRIENDS_ACTION)
    return table, await started_at(app, table)


async def run_job(app: FastAPI, table: dict, started: datetime, narrator=None, **options) -> None:
    """맡겨진 서술을 직접 돌린다. options 는 고르는 것들(lore, memories, histories)과 시간(budgets)이다."""
    await closing.narrate_round(
        app.state.session_factory, narrator or FakeNarrator(), uuid.UUID(table['id']), 1, started, **options
    )


class BrokenFinder:
    """고르다가 예외를 내는 것. 임베딩 모델의 실패가 아닌 예외다(DB 의 오류, 버그)."""

    async def find(self, request: NarrationRequest) -> list:
        raise RuntimeError('고르다가 DB 가 끊겼다')


class StuckFinder:
    """고르다가 돌아오지 않는 것."""

    async def find(self, request: NarrationRequest) -> list:
        await asyncio.Event().wait()
        return []


class StuckNarrator:
    """답하지 않는 서술자."""

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        await asyncio.Event().wait()
        return RESULT


class CountingNarrator:
    """몇 번 불렸는지 세는 서술자."""

    def __init__(self) -> None:
        self.calls = 0

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        self.calls += 1
        return RESULT


async def rounds_of(client: AsyncClient, headers: dict, table: dict) -> list[tuple[int, str]]:
    rounds = (await client.get(table_url(table, '/rounds'), headers=headers)).json()
    return [(round_['number'], round_['status']) for round_ in rounds['items']]


@pytest.mark.parametrize('broken', ['lore', 'memories', 'histories'])
async def test_a_search_that_breaks_does_not_stop_the_narration(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs, caplog, broken: str
):
    table, started = await hold_closing(client, app, me, friend)

    with caplog.at_level(logging.ERROR, logger='app.rounds.closing'):
        await run_job(app, table, started, **{broken: BrokenFinder()})

    # 고르지 못한 것 없이 서술하고 라운드를 닫는다. 실패를 알리지 않는다
    assert await rounds_of(client, me, table) == [(1, 'closed'), (2, 'open')]
    assert 'narration_failed' not in await event_types(client, me, table)
    # 버그일 수 있으므로 로그에는 남는다
    assert '고르지 못했다' in caplog.text


async def test_a_search_that_never_returns_is_given_up(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs, caplog
):
    table, started = await hold_closing(client, app, me, friend)
    narrator = GatedNarrator()
    narrator.release()

    with caplog.at_level(logging.WARNING, logger='app.rounds.closing'):
        async with asyncio.timeout(SOON):
            await run_job(app, table, started, narrator, lore=StuckFinder(), budgets=Budgets(retrieval=0.05))

    assert await rounds_of(client, me, table) == [(1, 'closed'), (2, 'open')]
    # 고르는 시간은 셋이 함께 쓴다. 로어북이 다 쓰면 지난 일과 이력도 고르지 않는다
    assert narrator.requests[0].lore == []
    assert '시간이 다 됐다' in caplog.text


async def test_a_narration_that_never_ends_is_cut_off_and_told(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs
):
    table, started = await hold_closing(client, app, me, friend)

    async with asyncio.timeout(SOON):
        with pytest.raises(TimeoutError):
            await run_job(app, table, started, StuckNarrator(), budgets=Budgets(job=0.2))

    # 실패가 적혀서 방장이 기다리지 않고 다시 맡길 수 있다
    assert (await last_event(client, me, table))['payload'] == {'round': 1, 'reason': 'timeout'}
    again = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    assert again.status_code == status.HTTP_202_ACCEPTED


async def test_a_job_whose_time_ran_out_before_it_started_does_not_narrate(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs
):
    table, started = await hold_closing(client, app, me, friend)
    narrator = CountingNarrator()

    # 닫기 시작한 때부터 센다. 맡긴 뒤에 오래 기다렸다가 돌면 남은 시간이 없다
    with pytest.raises(TimeoutError):
        await run_job(app, table, started, narrator, budgets=Budgets(job=0))

    assert narrator.calls == 0
    assert (await last_event(client, me, table))['payload'] == {'round': 1, 'reason': 'timeout'}


@pytest.mark.parametrize('step', ['load_closing_request', 'finish_closing'])
async def test_failing_to_read_or_to_save_the_round_is_told(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs, monkeypatch, step: str
):
    table, started = await hold_closing(client, app, me, friend)

    async def broken(*args, **kwargs):
        raise RuntimeError('DB 가 끊겼다')

    monkeypatch.setattr(service, step, broken)
    with pytest.raises(RuntimeError):
        await run_job(app, table, started)

    # 서술자의 실패가 아니어도 실패를 적는다. 라운드는 닫는 중에 머물고 바로 다시 맡길 수 있다
    assert (await last_event(client, me, table))['payload'] == {'round': 1, 'reason': 'error'}
    latest = await current(client, me, table)
    assert (latest['status'], latest['narration_failed_at'] is not None) == ('closing', True)


async def test_an_error_after_the_round_was_saved_is_not_told_as_a_failure(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs, monkeypatch
):
    table, started = await hold_closing(client, app, me, friend)
    finish = service.finish_closing

    async def finish_then_break(*args, **kwargs):
        # 저장은 끝났는데 그 뒤에 끊겼다(저장하는 도중에 작업이 끊긴 경우와 같다)
        await finish(*args, **kwargs)
        raise RuntimeError('저장한 뒤에 끊겼다')

    monkeypatch.setattr(service, 'finish_closing', finish_then_break)
    with pytest.raises(RuntimeError):
        await run_job(app, table, started)

    # 새 세션으로 실제 상태를 본다. 이미 닫힌 라운드에는 실패를 적지 않는다
    assert await rounds_of(client, me, table) == [(1, 'closed'), (2, 'open')]
    assert 'narration_failed' not in await event_types(client, me, table)


async def test_a_job_ends_even_when_the_failure_cannot_be_written(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs, monkeypatch, caplog
):
    table, started = await hold_closing(client, app, me, friend)

    async def stuck(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(service, 'fail_closing', stuck)
    with caplog.at_level(logging.ERROR, logger='app.rounds.closing'):
        async with asyncio.timeout(SOON):
            # 처음의 예외가 그대로 올라온다. 실패를 적지 못한 것이 그것을 가리지 않는다
            with pytest.raises(RuntimeError):
                await run_job(app, table, started, FailingNarrator(RuntimeError('버그')), budgets=Budgets(failure=0.05))

    assert '실패를 적지 못했다' in caplog.text
    # 적지 못했으므로 라운드는 닫는 중에 머문다. 한참 뒤에 다시 맡길 수 있다
    assert (await current(client, me, table))['narration_failed_at'] is None


async def hand_again(client: AsyncClient, app: FastAPI, me: dict, table: dict, monkeypatch) -> datetime:
    """닫는 중인 라운드를 다시 맡긴다. 새로 적힌 닫기 시작한 시각을 돌려준다."""
    monkeypatch.setattr(service, 'CLOSING_RETRY_SECONDS', 0)
    again = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    assert again.status_code == status.HTTP_202_ACCEPTED, again.text
    return await started_at(app, table)


async def test_handing_a_round_again_starts_a_new_run(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs, monkeypatch
):
    table, first = await hold_closing(client, app, me, friend)

    second = await hand_again(client, app, me, table, monkeypatch)

    assert second > first
    assert held.names == [f'narrate:{table["id"]}:1'] * 2


async def test_an_old_run_cannot_mark_the_new_one_as_failed(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs, monkeypatch
):
    table, first = await hold_closing(client, app, me, friend)
    second = await hand_again(client, app, me, table, monkeypatch)

    # 앞서 맡은 작업이 서술자를 기다리다가 늦게 실패했다. 지금 도는 서술의 라운드에 실패를 적지 못한다
    async with app.state.session_factory() as session:
        await service.fail_closing(session, uuid.UUID(table['id']), 1, first, 'timeout')

    assert 'narration_failed' not in await event_types(client, me, table)
    assert (await current(client, me, table))['narration_failed_at'] is None
    # 지금 맡은 작업의 실패는 적힌다
    async with app.state.session_factory() as session:
        await service.fail_closing(session, uuid.UUID(table['id']), 1, second, 'timeout')
    assert (await event_types(client, me, table)).count('narration_failed') == 1


async def test_an_old_run_cannot_close_the_round(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs, monkeypatch
):
    table, first = await hold_closing(client, app, me, friend)
    second = await hand_again(client, app, me, table, monkeypatch)
    narrator = CountingNarrator()

    # 이제 도는 옛 작업은 읽을 때 물러난다. 서술자를 부르지도 않는다
    await run_job(app, table, first, narrator)
    # 다시 맡기기 전에 이미 서술을 받아 둔 옛 작업도 닫지 못한다
    async with app.state.session_factory() as session:
        await service.finish_closing(session, uuid.UUID(table['id']), 1, first, '늦게 온 서술')

    assert narrator.calls == 0
    assert await rounds_of(client, me, table) == [(1, 'closing')]
    # 지금 맡은 작업이 닫는다
    await run_job(app, table, second, narrator)
    assert await rounds_of(client, me, table) == [(1, 'closed'), (2, 'open')]
    assert (await current(client, me, table))['scene'] == RESULT


NOON = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ('elapsed', 'left'),
    [
        (0, 195.0),
        (60, 135.0),
        # 다 썼으면 0 이다. 음수가 되지 않는다
        (195, 0.0),
        (500, 0.0),
    ],
)
def test_the_time_left_is_counted_from_when_the_round_began_closing(elapsed: float, left: float):
    assert seconds_left(NOON, NOON + timedelta(seconds=elapsed), 195.0) == left


def test_a_job_ends_before_the_round_can_be_handed_again():
    # 작업이 살아 있을 수 있는 시간(끊기기까지 + 실패를 적기까지)이 다시 맡길 수 있는 때보다 짧다
    assert service.CLOSING_JOB_SECONDS + service.FAILURE_RECORD_SECONDS < service.CLOSING_RETRY_SECONDS
    # 고르기와 서술이 제 시간을 다 써도 마무리할 시간이 남는다
    longest = service.RETRIEVAL_BUDGET_SECONDS + service.NARRATION_BUDGET_SECONDS
    assert longest < service.CLOSING_JOB_SECONDS
    assert Budgets() == Budgets(
        job=service.CLOSING_JOB_SECONDS,
        retrieval=service.RETRIEVAL_BUDGET_SECONDS,
        failure=service.FAILURE_RECORD_SECONDS,
    )


# --- 서술하는 사이에 테이블이 끝나면 ---


async def test_a_table_that_ends_while_the_gm_narrates_opens_no_next_round(
    client: AsyncClient, me: dict, friend: dict, narrator: GatedNarrator, narrated
):
    table = await start_duo(client, me, friend)
    await begin_closing(client, me, friend, table, narrator)

    ended = await client.post(table_url(table, '/end'), headers=me)
    narrator.release()
    await narrated()

    assert ended.status_code == status.HTTP_200_OK
    # 라운드는 닫히지만 다음 라운드는 열리지 않는다. 끝난 테이블에 열린 라운드가 남지 않는다
    rounds = (await client.get(table_url(table, '/rounds'), headers=me)).json()
    assert [(round_['number'], round_['status']) for round_ in rounds['items']] == [(1, 'closed')]
    # 서술은 쓸 곳이 없어 버려진다
    assert await event_types(client, me, table) == ['player_action', 'player_action', 'round_closed', 'table_ended']


# --- 얼마나 지나야 다시 맡길 수 있나 ---


# 이 테스트들의 "지금". 실제 시계를 읽지 않는다. 읽으면 테스트를 모으는 때와 돌리는 때 사이에 시간이 흐른다
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_round(closing_ago: float | None, closed: bool = False, failed: bool = False) -> Round:
    """닫기 시작한 지 closing_ago 초 된 라운드. None 이면 아직 선언을 받는 중이다. failed 면 서술이 실패했다."""
    closing_at = None if closing_ago is None else NOW - timedelta(seconds=closing_ago)
    return Round(
        number=1,
        scene='장면',
        closing_at=closing_at,
        closed_at=NOW if closed else None,
        narration_failed_at=NOW if failed else None,
    )


@pytest.mark.parametrize(
    ('round_', 'expected'),
    [
        # 선언을 받는 중인 라운드는 멈춘 것이 아니다
        (make_round(None), False),
        # 방금 맡겼다. 서술이 돌고 있을 것이다
        (make_round(1), False),
        (make_round(service.CLOSING_RETRY_SECONDS - 1), False),
        # 한참 지났다. 맡은 작업이 사라졌다
        (make_round(service.CLOSING_RETRY_SECONDS), True),
        (make_round(service.CLOSING_RETRY_SECONDS + 1), True),
        # 닫힌 라운드는 아무리 오래돼도 멈춘 것이 아니다
        (make_round(service.CLOSING_RETRY_SECONDS + 1, closed=True), False),
        # 서술이 끝내 실패했다. 방금이어도 다시 맡길 수 있다
        (make_round(1, failed=True), True),
        # 닫힌 라운드는 실패가 적혀 있어도 다시 맡길 것이 없다
        (make_round(1, closed=True, failed=True), False),
    ],
)
def test_a_round_is_stalled_only_after_closing_for_a_long_time(round_: Round, expected: bool):
    assert service.is_stalled(round_, NOW) is expected
