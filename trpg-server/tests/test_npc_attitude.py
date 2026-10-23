# trpg-server/tests/test_npc_attitude.py

"""
NPC 의 태도(우호, 중립, 적대, #474)를 검증한다.

판은 test_npc_actions.py 의 것과 같다. 스타팅에 악역영애(진짜 이름은 비올레타)가 나온다. 드워프는 나오지 않는다.

보는 것.
  - 시나리오: 인물의 NPC 시트에 처음 태도를 적고 판에 굳힌다. 비우면 중립, 모르는 태도는 거부한다.
    옛 판의 인물과 시트가 없는 인물은 중립이다(판 형식 37).
  - 테이블: 시작할 때 판의 태도로 만든다. 장면의 인물 목록에 실린다. 서술의 인물 줄에 붙는다(중립이면 붙지 않는다).
  - 바꾸기: 엔진만 바꾼다. 같은 태도면 아무 일도 없다. 바뀌면 이벤트에 장면의 호칭과 까닭이 적힌다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import NpcAttitude
from app.assets.scenarios.snapshot import Snapshot, npc_attitude_of
from app.assets.scenarios.upgrades import upgrade_from_36
from app.events.models import EventType
from app.rounds import records
from app.rounds.narrator import PersonState
from app.rounds.prompt import person_line
from app.tables.models import TableNpc
from app.tables.npc_attitudes import attitude_word, change_attitude
from tests.narration_model import asset_body
from tests.sheets import SHEET, make_sheet
from tests.test_npc_actions import LOREBOOKS_URL, OPENING, RULEBOOKS_URL, SCENARIOS_URL, TABLES_URL, post, table_url
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
LADY_SHEET = make_sheet(max_hp=10)


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    return {'Authorization': f'Bearer {make_token(signing_key, make_access_claims(sub=str(ME)))}'}


async def make_lore(client: AsyncClient, me: dict) -> dict:
    lorebook = await post(client, LOREBOOKS_URL, me, title='추격전의 인물들')
    entries = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    lady = await post(client, entries, me, name='비올레타', keywords=['악역영애'], content='끄나풀', kind='person')
    dwarf = await post(client, entries, me, name='드워프', keywords=['망치'], content='추격자', kind='person')
    return {'lorebook': lorebook, 'lady': lady, 'dwarf': dwarf}


async def make_scenario(client: AsyncClient, me: dict, lore: dict, npc_sheets: list[dict]) -> dict:
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    return await post(
        client,
        SCENARIOS_URL,
        me,
        title='열일곱 행성 추격전',
        rulebook_id=rulebook['id'],
        lorebook_ids=[lore['lorebook']['id']],
        openings=[OPENING],
        default_sheet=SHEET,
        npc_sheets=npc_sheets,
        default_npc_sheet=make_sheet(max_hp=6),
    )


async def start(client: AsyncClient, me: dict, attitude: str | None) -> dict:
    """악역영애의 시트에 그 태도(None 이면 적지 않음)를 단 시나리오로 테이블을 시작한다."""
    lore = await make_lore(client, me)
    sheet = {'entry_id': lore['lady']['id'], 'sheet': LADY_SHEET}
    scenario = await make_scenario(client, me, lore, [sheet if attitude is None else {**sheet, 'attitude': attitude}])
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {**lore, 'table': table}


# --- 시나리오 ---


async def test_an_attitude_is_saved_and_published(client: AsyncClient, me: dict):
    lore = await make_lore(client, me)
    sheets = [
        {'entry_id': lore['lady']['id'], 'sheet': LADY_SHEET, 'attitude': 'hostile'},
        {'entry_id': lore['dwarf']['id'], 'sheet': LADY_SHEET},
    ]
    scenario = await make_scenario(client, me, lore, sheets)

    response = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)

    assert [sheet['attitude'] for sheet in scenario['npc_sheets']] == ['hostile', 'neutral']
    assert [sheet['attitude'] for sheet in response.json()['snapshot']['npc_sheets']] == ['hostile', 'neutral']


async def test_an_unknown_attitude_is_refused(client: AsyncClient, me: dict):
    lore = await make_lore(client, me)
    sheet = {'entry_id': lore['lady']['id'], 'sheet': LADY_SHEET, 'attitude': 'smitten'}
    body = {'title': '추격전', 'npc_sheets': [sheet]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_a_person_without_a_sheet_is_neutral():
    snapshot = Snapshot.model_construct(npc_sheets=[])

    assert npc_attitude_of(snapshot, uuid.uuid4()) == NpcAttitude.NEUTRAL


def test_an_old_snapshot_reads_everyone_as_neutral():
    sheet = {'entry_id': str(uuid.uuid4()), 'sheet': SHEET}
    document = {'format': 36, 'npc_sheets': [sheet]}

    upgraded = upgrade_from_36(document)

    assert upgraded['format'] == 37
    assert upgraded['npc_sheets'] == [{**sheet, 'attitude': 'neutral'}]
    assert 'attitude' not in document['npc_sheets'][0]


# --- 테이블 ---


@pytest.mark.parametrize(
    ('attitude', 'expected'), [('hostile', 'hostile'), ('friendly', 'friendly'), (None, 'neutral')]
)
async def test_the_table_starts_with_the_written_attitude(
    client: AsyncClient, me: dict, session: AsyncSession, attitude: str | None, expected: str
):
    world = await start(client, me, attitude)

    response = await client.get(table_url(world['table'], '/rounds/current/people'), headers=me)

    (lady,) = response.json()['people']
    assert lady['attitude'] == expected
    # 시트가 없는 드워프는 중립이다(장면에 나오지 않아 목록에는 없다)
    query = select(TableNpc).where(TableNpc.entry_id == uuid.UUID(world['dwarf']['id']))
    dwarf = await session.scalar(query)
    assert dwarf.attitude == 'neutral'


async def test_the_narrator_sees_the_attitude(client: AsyncClient, app: FastAPI, me: dict, narrated):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    world = await start(client, me, 'hostile')

    response = await client.put(
        table_url(world['table'], '/rounds/current/declaration'), json={'content': '주위를 살핀다.'}, headers=me
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    await narrated()

    (request,) = narrator.requests
    assert [(person.name, person.attitude) for person in request.people] == [('악역영애', '적대')]


@pytest.mark.parametrize(
    ('attitude', 'line'),
    [
        ('적대', '- 악역영애: 다침. 태도: 적대'),
        (None, '- 악역영애: 다침'),
    ],
)
def test_the_person_line_shows_only_a_non_neutral_attitude(attitude: str | None, line: str):
    assert person_line(PersonState(name='악역영애', condition='다침', attitude=attitude)) == line


# --- 바꾸기 ---


def npc(attitude: str = 'neutral') -> TableNpc:
    return TableNpc(entry_id=uuid.uuid4(), attitude=attitude)


def test_changing_the_attitude_returns_what_to_record():
    state = npc()

    change = change_attitude(state, NpcAttitude.HOSTILE, 'caught_stealing')

    assert state.attitude == NpcAttitude.HOSTILE
    assert change == {
        'entry_id': str(state.entry_id),
        'previous': NpcAttitude.NEUTRAL,
        'attitude': NpcAttitude.HOSTILE,
        'reason': 'caught_stealing',
    }


def test_the_same_attitude_changes_nothing():
    state = npc('hostile')

    assert change_attitude(state, NpcAttitude.HOSTILE, 'caught_stealing') is None
    assert state.attitude == 'hostile'


@pytest.mark.parametrize(('attitude', 'word'), [('friendly', '우호'), ('neutral', None), ('hostile', '적대')])
def test_the_word_for_the_narrator(attitude: str, word: str | None):
    assert attitude_word(npc(attitude)) == word


def test_a_change_is_recorded_with_the_scene_name(monkeypatch: pytest.MonkeyPatch):
    recorded = []
    monkeypatch.setattr(records.recorder, 'record', lambda *args, **kwargs: recorded.append((args, kwargs)))
    change = change_attitude(npc(), NpcAttitude.HOSTILE, 'caught_stealing')
    cause = SimpleNamespace(payload={'round': 3})

    records.record_attitude_change(None, None, change, '악역영애', cause)

    ((args, kwargs),) = recorded
    assert args[2] == EventType.NPC_ATTITUDE_CHANGED
    assert kwargs['payload'] == {**change, 'round': 3, 'name': '악역영애'}
    assert kwargs['cause'] is cause
