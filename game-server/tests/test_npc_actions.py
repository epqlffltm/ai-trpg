# game-server/tests/test_npc_actions.py

"""
행동이 NPC 를 겨누는 것(#111 ②)을 검증한다.

장면은 스타팅이다. 악역영애(진짜 이름은 비올레타)가 나오고, 드워프는 나오지 않는다. 고속도로는 장소다.
주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다. 판정의 눈을 먼저, 양의 눈을 그다음에 쓴다.

보는 것은 다섯이다.
  - 이번 장면의 인물: 장면에 나온 인물만, 장면의 호칭으로 보인다. 겨눌 수 있는 것은 그 인물뿐이다.
  - 타격과 회복: 성공하면 NPC 의 HP 와 생사가 바뀐다. 제압은 쓰러뜨리고, 죽이려는 타격은 죽인다.
  - 받을 때와 닫을 때의 검사: 장면에 없는 인물, 죽은 인물, 같은 라운드에 앞사람이 죽인 인물.
  - 내보내는 것: 응답과 이벤트에 HP 의 숫자가 없다.
  - 서술: 몸 상태를 말로 받는다. 서술을 다시 맡겨도 상태가 다시 바뀌지 않는다.
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import Snapshot
from app.engine.dice import ScriptedDice
from app.engine.health import ChangeKind
from app.engine.templates import SRD5
from app.main import API_PREFIX
from app.rounds import prompt, service
from app.rounds.cast import cast_of, condition_of
from app.rounds.narrator import NO_PREVIEW, NarrationRequest, NpcImpact, PersonState, Preview, describe_npc_impact
from app.tables.models import NpcStatus, TableNpc
from app.tables.npcs import change_npc, status_after
from tests.sheets import SHEET, make_sheet
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')

OPENING = '사이렌이 울린다. 리무진의 문이 열리고 악역영애가 부채를 펼친다. 우주 고속도로는 꽉 막혔다.'
# 악역영애의 숫자. 최대 HP 가 10 이다. 다른 인물은 기본 NPC 시트(최대 HP 6)를 받는다
LADY_SHEET = make_sheet(cha=16, max_hp=10)
NPC_DEFAULT = make_sheet(max_hp=6)

# 판정의 눈. 보통(목표 15)에 도전한다. 시트의 보정은 0 이다
FAIL = 1
PASS = 20
# 부상 표(d20)의 눈. 1~10 은 부상이 없다. 큰 타격(최대 HP 의 절반 이상)이나 쓰러짐에 굴린다.
# 죽은 인물에게는 굴리지 않는다
NO_INJURY = 1

PUNCH = '악역영애에게 주먹을 날린다.'
TEND = '악역영애의 상처를 싸맨다.'
LAUGH = '크게 웃는다.'


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 방장이다. 캐릭터는 '엘프'다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """두 번째로 앉는 사람. 캐릭터는 '드워프 기사'다."""
    return bearer(signing_key, FRIEND)


def load_dice(app: FastAPI, rolls: list[int]) -> ScriptedDice:
    """앱의 주사위를 정해진 눈을 내는 것으로 바꿔 꽂는다."""
    dice = ScriptedDice(rolls)
    app.state.dice = dice
    return dice


def punch(npc: str, harm: str = 'moderate', lethal: bool = False) -> dict:
    """근력으로 보통에 도전한다. 성공하면 그 NPC 가 다친다."""
    return {'kind': 'check', 'ability': 'str', 'difficulty': 'medium', 'harm': harm, 'npc': npc, 'lethal': lethal}


def tend(npc: str, recover: str = 'light') -> dict:
    """지혜로 보통에 도전한다. 성공하면 그 NPC 가 회복한다."""
    return {'kind': 'check', 'ability': 'wis', 'difficulty': 'medium', 'recover': recover, 'npc': npc}


async def post(client: AsyncClient, url: str, headers: dict[str, str], **body) -> dict:
    response = await client.post(url, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def table_url(table: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{table["id"]}{path}'


async def start_table(client: AsyncClient, me: dict[str, str], *others: dict[str, str]) -> dict:
    """
    인물 둘과 장소 하나가 든 로어북을 붙인 시나리오로 테이블을 시작한다. 나와 others 가 앉는다.

    돌려주는 것은 테이블과 항목들이다(lady, dwarf, highway).
    """
    lorebook = await post(client, LOREBOOKS_URL, me, title='추격전의 인물들')
    entries_url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    lady = await post(
        client, entries_url, me, name='비올레타', keywords=['악역영애'], content='경찰의 끄나풀', kind='person'
    )
    dwarf = await post(client, entries_url, me, name='드워프', keywords=['망치'], content='추격자', kind='person')
    highway = await post(client, entries_url, me, name='우주 고속도로', keywords=[], content='길', kind='place')
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    scenario = await post(
        client,
        SCENARIOS_URL,
        me,
        title='열일곱 행성 추격전',
        rulebook_id=rulebook['id'],
        lorebook_ids=[lorebook['id']],
        openings=[OPENING],
        default_sheet=SHEET,
        npc_sheets=[{'entry_id': lady['id'], 'sheet': LADY_SHEET}],
        default_npc_sheet=NPC_DEFAULT,
    )
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1 + len(others))
    names = ['엘프', '드워프 기사']
    for headers, name in zip([me, *others], names, strict=False):
        if headers is not me:
            await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
        await client.put(table_url(table, '/character'), json={'name': name}, headers=headers)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {'table': table, 'lady': lady, 'dwarf': dwarf, 'highway': highway}


async def send(client: AsyncClient, headers: dict[str, str], table: dict, content: str, action: dict | None = None):
    body = {'content': content} if action is None else {'content': content, 'action': action}
    return await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=headers)


async def declare(
    client: AsyncClient, headers: dict[str, str], table: dict, content: str, action: dict | None = None
) -> dict:
    response = await send(client, headers, table, content, action)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def people(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    response = await client.get(table_url(table, '/rounds/current/people'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def state_of(session: AsyncSession, table: dict, entry: dict) -> tuple[int, str]:
    """DB 에 적힌 NPC 의 (HP, 생사)."""
    query = select(TableNpc).where(
        TableNpc.table_id == uuid.UUID(table['id']), TableNpc.entry_id == uuid.UUID(entry['id'])
    )
    npc = await session.scalar(query.execution_options(populate_existing=True))
    return npc.hp, npc.status


def npc_effect(round_: dict) -> dict | None:
    """라운드의 첫 선언에 적힌 NPC 의 변화."""
    return round_['declarations'][0]['outcome']['npc_effect']


async def events_of(client: AsyncClient, headers: dict[str, str], table: dict, type_: str) -> list[dict]:
    response = await client.get(table_url(table, '/events'), params={'limit': 100}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return [event for event in response.json()['items'] if event['type'] == type_]


class RecordingNarrator:
    """받은 것을 적어 두는 서술자. fail_first 면 처음 한 번은 실패한다. 장면에는 악역영애를 다시 부른다."""

    def __init__(self, fail_first: bool = False) -> None:
        self.requests: list[NarrationRequest] = []
        self.fail_first = fail_first

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        self.requests.append(request)
        if self.fail_first and len(self.requests) == 1:
            raise RuntimeError('서술자가 답하지 못했다')
        return '악역영애가 비틀거린다.'


# --- 이번 장면의 인물 ---


async def test_only_the_people_in_the_scene_are_listed(client: AsyncClient, me: dict[str, str]):
    world = await start_table(client, me)

    cast = await people(client, me, world['table'])

    # 드워프는 장면에 나오지 않았고, 고속도로는 인물이 아니다. 이름은 장면의 호칭이다. 진짜 이름은 아직 드러나지 않았다
    lady = {'id': world['lady']['id'], 'name': '악역영애', 'status': 'alive', 'injuries': []}
    assert cast == {'round': 1, 'people': [lady]}


async def test_only_the_seated_see_the_people(client: AsyncClient, me: dict[str, str], signing_key: SigningKey):
    world = await start_table(client, me)

    response = await client.get(
        table_url(world['table'], '/rounds/current/people'), headers=bearer(signing_key, STRANGER)
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_a_table_started_without_npc_states_has_no_people(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    # NPC 의 상태가 생기기 전에 시작한 테이블
    await session.execute(text('DELETE FROM table_npcs'))
    await session.commit()

    assert (await people(client, me, world['table']))['people'] == []
    response = await send(client, me, world['table'], PUNCH, punch(world['lady']['id']))
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 타격 ---


async def test_a_successful_hit_hurts_the_npc(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    # 4 는 최대 HP(10)의 절반에 못 미친다. 부상 표를 굴리지 않는다
    load_dice(app, [PASS, 4])

    closing = await declare(client, me, world['table'], PUNCH, punch(world['lady']['id']))

    # HP 의 숫자는 응답에 없다
    assert npc_effect(closing) == {
        'kind': 'damage',
        'magnitude': 'moderate',
        'entry_id': world['lady']['id'],
        'name': '악역영애',
        'rolls': [4],
        'amount': 4,
        'lethal': False,
        'status': 'alive',
        'injury_roll': None,
    }
    assert closing['declarations'][0]['outcome']['effect'] is None
    assert await state_of(session, world['table'], world['lady']) == (6, NpcStatus.ALIVE)


async def test_a_missed_hit_changes_nothing(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    dice = load_dice(app, [FAIL, 5])

    closing = await declare(client, me, world['table'], PUNCH, punch(world['lady']['id']))

    assert npc_effect(closing) is None
    assert await state_of(session, world['table'], world['lady']) == (10, NpcStatus.ALIVE)
    # 양을 정하는 주사위는 굴리지 않았다
    assert dice.remaining == 1


async def test_a_missed_hit_still_costs_its_risk(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    world = await start_table(client, me)
    load_dice(app, [FAIL, 3])

    closing = await declare(client, me, world['table'], PUNCH, {**punch(world['lady']['id']), 'risk': 'light'})

    outcome = closing['declarations'][0]['outcome']
    assert (outcome['effect']['after'], outcome['npc_effect']) == (7, None)


async def test_subduing_to_zero_knocks_the_npc_down(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    load_dice(app, [PASS, 8, 8, NO_INJURY])

    closing = await declare(client, me, world['table'], PUNCH, punch(world['lady']['id'], 'heavy'))

    assert npc_effect(closing)['status'] == 'downed'
    assert await state_of(session, world['table'], world['lady']) == (0, NpcStatus.DOWNED)


async def test_a_lethal_hit_to_zero_kills_the_npc(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    load_dice(app, [PASS, 8, 8])

    closing = await declare(client, me, world['table'], PUNCH, punch(world['lady']['id'], 'heavy', lethal=True))

    assert (npc_effect(closing)['status'], npc_effect(closing)['lethal']) == ('dead', True)
    assert await state_of(session, world['table'], world['lady']) == (0, NpcStatus.DEAD)


async def test_a_lethal_hit_that_leaves_hp_only_hurts(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    load_dice(app, [PASS, 3])

    await declare(client, me, world['table'], PUNCH, punch(world['lady']['id'], 'light', lethal=True))

    assert await state_of(session, world['table'], world['lady']) == (7, NpcStatus.ALIVE)


async def test_a_downed_npc_dies_to_a_lethal_hit_and_rises_with_healing(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, narrated
):
    world = await start_table(client, me)
    table, lady = world['table'], world['lady']
    load_dice(app, [PASS, 8, 8, NO_INJURY])
    await declare(client, me, table, PUNCH, punch(lady['id'], 'heavy'))
    await narrated()

    # 다음 장면(가짜 서술자의 글)에도 악역영애가 나온다. 쓰러진 채로 겨눌 수 있다
    assert (await people(client, me, table))['people'][0]['status'] == 'downed'
    load_dice(app, [PASS, 2])
    await declare(client, me, table, TEND, tend(lady['id']))
    await narrated()
    assert await state_of(session, table, lady) == (2, NpcStatus.ALIVE)

    load_dice(app, [PASS, 8, 8, NO_INJURY])
    await declare(client, me, table, PUNCH, punch(lady['id'], 'heavy'))
    await narrated()
    load_dice(app, [PASS, 1])
    await declare(client, me, table, PUNCH, punch(lady['id'], 'light', lethal=True))
    assert await state_of(session, table, lady) == (0, NpcStatus.DEAD)


async def test_healing_does_not_pass_the_maximum(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, narrated
):
    world = await start_table(client, me)
    load_dice(app, [PASS, 3])
    await declare(client, me, world['table'], PUNCH, punch(world['lady']['id'], 'light'))
    await narrated()

    load_dice(app, [PASS, 8])
    await declare(client, me, world['table'], TEND, tend(world['lady']['id'], 'moderate'))

    assert await state_of(session, world['table'], world['lady']) == (10, NpcStatus.ALIVE)


# --- 받을 때와 닫을 때의 검사 ---


async def test_a_person_not_in_the_scene_cannot_be_aimed_at(client: AsyncClient, me: dict[str, str]):
    world = await start_table(client, me)

    absent = await send(client, me, world['table'], PUNCH, punch(world['dwarf']['id']))
    place = await send(client, me, world['table'], PUNCH, punch(world['highway']['id']))
    unknown = await send(client, me, world['table'], PUNCH, punch(str(uuid.uuid4())))

    # 셋 다 같은 답이다. 장면에 나오지 않은 것이 무엇인지 알려 주지 않는다
    for response in (absent, place, unknown):
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json() == {'detail': 'action.npc 가 이번 장면의 인물이 아닙니다.'}


async def test_a_dead_npc_cannot_be_aimed_at(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    world = await start_table(client, me)
    load_dice(app, [PASS, 8, 8])
    await declare(client, me, world['table'], PUNCH, punch(world['lady']['id'], 'heavy', lethal=True))
    await narrated()

    hit = await send(client, me, world['table'], PUNCH, punch(world['lady']['id']))
    heal = await send(client, me, world['table'], TEND, tend(world['lady']['id']))

    # 죽은 인물도 장면에는 남아 있다. 겨누지는 못한다
    assert (await people(client, me, world['table']))['people'][0]['status'] == 'dead'
    for response in (hit, heal):
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()['reason'] == 'npc_dead'


async def test_an_npc_killed_earlier_in_the_round_is_not_changed_again(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me, friend)
    table, lady = world['table'], world['lady']
    dice = load_dice(app, [PASS, 8, 8, PASS, 4])

    await declare(client, me, table, PUNCH, punch(lady['id'], 'heavy', lethal=True))
    closing = await declare(client, friend, table, TEND, tend(lady['id']))

    effects = [declaration['outcome']['npc_effect'] for declaration in closing['declarations']]
    # 판정은 굴렸지만 회복의 양은 굴리지 않았다. 죽은 인물은 되살아나지 않는다
    assert [effect and effect['status'] for effect in effects] == ['dead', None]
    assert dice.remaining == 1
    assert await state_of(session, table, lady) == (0, NpcStatus.DEAD)


async def test_an_npc_downed_earlier_in_the_round_can_be_helped_up(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me, friend)
    load_dice(app, [PASS, 8, 8, NO_INJURY, PASS, 4])

    await declare(client, me, world['table'], PUNCH, punch(world['lady']['id'], 'heavy'))
    await declare(client, friend, world['table'], TEND, tend(world['lady']['id']))

    assert await state_of(session, world['table'], world['lady']) == (4, NpcStatus.ALIVE)


async def test_a_harm_the_rules_do_not_have_is_refused(client: AsyncClient, me: dict[str, str]):
    world = await start_table(client, me)

    response = await send(client, me, world['table'], PUNCH, punch(world['lady']['id'], 'deadly'))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {'detail': 'action.harm 가 이 테이블의 규칙에 없습니다.'}


# --- 내보내는 것 ---


async def test_the_change_is_recorded_without_hp_numbers(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    load_dice(app, [PASS, 4])

    await declare(client, me, world['table'], PUNCH, punch(world['lady']['id']))

    (changed,) = await events_of(client, me, world['table'], 'npc_changed')
    (rolled,) = await events_of(client, me, world['table'], 'check_rolled')
    assert changed['payload'] == {
        'round': 1,
        'entry_id': world['lady']['id'],
        'name': '악역영애',
        'kind': 'damage',
        'magnitude': 'moderate',
        'rolls': [4],
        'amount': 4,
        'lethal': False,
        'status': 'alive',
        'injury_roll': None,
    }
    assert changed['caused_by_sequence'] == rolled['sequence']
    assert changed['actor_id'] is None
    # 장부에는 숫자까지 다 있다. 내보낼 때만 뺀다
    stored = await session.scalar(text("SELECT payload FROM table_events WHERE type = 'npc_changed'"))
    assert (stored['before'], stored['after'], stored['max_hp'], stored['status_before']) == (10, 6, 10, 'alive')


# --- 서술 ---


async def test_the_narrator_gets_the_condition_in_words(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    world = await start_table(client, me)
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    load_dice(app, [PASS, 4])

    await declare(client, me, world['table'], PUNCH, punch(world['lady']['id']))
    await narrated()

    (request,) = narrator.requests
    # 10 에서 6 이 됐다. 절반을 넘게 남았다
    assert request.people == [PersonState(name='악역영애', condition='다침')]
    assert request.moves[0].verdict.npc_impact == NpcImpact(kind='damage', name='악역영애', amount=4, condition='다침')
    text_ = '\n'.join(message.content for message in prompt.build_messages(request))
    assert '- 악역영애: 다침' in text_
    assert '→ 악역영애 피해 4 (다침)' in text_


async def test_narrating_again_does_not_change_the_npc_again(
    client: AsyncClient,
    app: FastAPI,
    me: dict[str, str],
    session: AsyncSession,
    narrated,
    monkeypatch: pytest.MonkeyPatch,
):
    world = await start_table(client, me)
    narrator = RecordingNarrator(fail_first=True)
    app.state.narrator = narrator
    load_dice(app, [PASS, 4])
    await declare(client, me, world['table'], PUNCH, punch(world['lady']['id']))
    await narrated()

    dice = load_dice(app, [PASS, 4])
    monkeypatch.setattr(service, 'CLOSING_RETRY_SECONDS', 0)
    again = await client.post(table_url(world['table'], '/rounds/current/close'), headers=me)
    await narrated()

    assert again.status_code == status.HTTP_202_ACCEPTED
    assert dice.remaining == 2
    assert await state_of(session, world['table'], world['lady']) == (6, NpcStatus.ALIVE)
    assert narrator.requests[0] == narrator.requests[1]
    assert len(await events_of(client, me, world['table'], 'npc_changed')) == 1


# --- 작은 함수들. DB 를 쓰지 않는다 ---


def npc_state(hp: int, max_hp: int = 10, npc_status: NpcStatus = NpcStatus.ALIVE) -> TableNpc:
    return TableNpc(table_id=uuid.uuid4(), entry_id=uuid.uuid4(), abilities={}, max_hp=max_hp, hp=hp, status=npc_status)


@pytest.mark.parametrize(
    ('hp', 'lethal', 'expected'),
    [
        (3, False, NpcStatus.ALIVE),
        (3, True, NpcStatus.ALIVE),
        (0, False, NpcStatus.DOWNED),
        (0, True, NpcStatus.DEAD),
    ],
)
def test_the_status_follows_the_hp_and_the_intent(hp: int, lethal: bool, expected: NpcStatus):
    assert status_after(hp, lethal) == expected


def test_healing_ignores_the_intent():
    npc = npc_state(0, npc_status=NpcStatus.DOWNED)
    light = next(magnitude for magnitude in SRD5.magnitudes if magnitude.key == 'light')

    change = change_npc(npc, ChangeKind.RECOVERY, light, True, ScriptedDice([2]))

    assert (change.after, npc.hp, npc.status) == (2, 2, NpcStatus.ALIVE)


@pytest.mark.parametrize(
    ('npc', 'expected'),
    [
        (npc_state(10), '멀쩡함'),
        (npc_state(9), '다침'),
        (npc_state(6), '다침'),
        (npc_state(5), '크게 다침'),
        (npc_state(1), '크게 다침'),
        (npc_state(0, npc_status=NpcStatus.DOWNED), '쓰러짐(의식 없음)'),
        (npc_state(0, npc_status=NpcStatus.DEAD), '죽음'),
    ],
)
def test_the_condition_is_told_in_words(npc: TableNpc, expected: str):
    assert condition_of(npc) == expected


def snapshot_with(entries: list[dict]) -> Snapshot:
    """인물 항목들이 든 판. 나머지는 테스트에 쓰지 않는 최소한의 값이다."""
    return Snapshot.model_validate(
        {
            'title': '추격전',
            'description': '',
            'rating': 'all',
            'openings': [OPENING],
            'recommended_players': {'min': 1, 'max': 4},
            'pregens': [],
            'character_modes': ['custom'],
            'default_sheet': SHEET,
            'npc_sheets': [],
            'default_npc_sheet': NPC_DEFAULT,
            'player_made_hp': None,
            'reroll_allowed': False,
            'narration_style': 'classic',
            'rulebook': {
                'id': str(uuid.uuid4()),
                'title': '룰북',
                'gm_guide': '',
                'rules': SRD5.model_dump(mode='json'),
            },
            'world': None,
            'lorebooks': [{'id': str(uuid.uuid4()), 'title': '인물', 'entries': entries}],
        }
    )


def person(name: str, keywords: list[str]) -> dict:
    return {'id': str(uuid.uuid4()), 'name': name, 'keywords': keywords, 'content': '', 'kind': 'person'}


def test_the_cast_is_in_the_order_of_the_people_and_named_as_in_the_scene():
    lady, cook, knight = person('비올레타', ['악역영애', '영애']), person('수프 아줌마', []), person('기사', [])
    snapshot = snapshot_with([lady, cook, knight])
    states = [npc_state(10) for _ in range(3)]
    for state, entry in zip(states, [lady, cook, knight], strict=True):
        state.entry_id = uuid.UUID(entry['id'])

    cast = cast_of(snapshot, '수프 아줌마가 손을 흔든다. 옆에서 악역영애가 웃는다.', reversed(states))

    # 키워드 중 장면에 나온 가장 긴 것이 호칭이다. 기사는 나오지 않았다
    assert [(member.name, str(member.entry_id)) for member in cast] == [
        ('악역영애', lady['id']),
        ('수프 아줌마', cook['id']),
    ]


def test_a_person_without_a_state_is_not_in_the_cast():
    lady = person('비올레타', ['악역영애'])

    assert cast_of(snapshot_with([lady]), '악역영애가 웃는다.', []) == []


def test_people_lines_tell_the_rules_of_downed_and_dead():
    lines = prompt.people_lines([PersonState('악역영애', '쓰러짐(의식 없음)')])

    assert lines == [prompt.PEOPLE_TITLE, prompt.PEOPLE_NOTE, '- 악역영애: 쓰러짐(의식 없음)', '']
    assert '말하거나 움직이지 않는다' in prompt.PEOPLE_NOTE
    assert prompt.people_lines([]) == []


def test_an_npc_impact_shows_only_the_amount():
    impact = NpcImpact(kind='recovery', name='악역영애', amount=3, condition='크게 다침')

    assert describe_npc_impact(impact) == '→ 악역영애 회복 3 (크게 다침)'
