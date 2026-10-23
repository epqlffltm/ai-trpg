# trpg-server/tests/test_npc_places.py

"""
인물의 자리(#282)를 검증한다. 판에 처음 있는 장소를 적은 인물은 글이 아니라 장소로 장면에 든다.

맵과 픽스처는 tests/test_table_map.py 의 것이다. 방장(기사)과 함께 앉는 사람(약사), 성문(시작)-광장 큰길,
광장→지하실 숨긴 길, 성문-숲 안개 길, 탑은 명소. 여기에 인물 셋, 사건 항목 하나, 맵 밖의 장소(지하 감옥)를 더한다.
  - 경비대장(진짜 이름 알베르트, 키워드 경비·경비대장): 성문에 있다. 스타팅에 나오지 않는다.
  - 대장장이(진짜 이름 한스, 키워드 대장장이): 광장에 있다. 스타팅에 나온다.
  - 은자(키워드 노인): 자리가 없다. 스타팅에 나온다.

보는 것.
  - 시나리오: 자리를 저장하고 판에 굳힌다. 잘못 둔 것은 422, 게시할 수 없는 것은 409 의 문제다.
    옛 판은 자리가 없는 것으로 읽는다.
  - 장면: 자리가 있는 인물은 캐릭터가 선 장소에 있을 때만 든다. 글에 나와도 아무도 없는 곳의 인물은 들지 않는다.
    글에 나오지 않고 든 인물은 가장 긴 키워드로 부른다. 자리가 없는 인물은 지금처럼 글로 든다.
  - 겨누기: 자리가 있는 인물은 같은 장소에 선 캐릭터만 겨눈다(판정, 치료, 훔치기, 빼앗기, 거래).
    싸우는 인물도 같은 장소의 캐릭터만 친다.
  - 사건: move_npc 가 인물을 옮긴다. 죽은 인물은 남는다. 이벤트에는 싣지 않고, 서술은 일행이 본 것만 받는다.
  - 서술: 자리가 있는 인물의 상태 줄에 장소가 붙는다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import HappeningEffectKind
from app.assets.scenarios.snapshot import HappeningEffectSnapshot, Snapshot, read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_49
from app.engine.action import LootAction, TreatAction
from app.rounds import prompt, trades
from app.rounds.acceptance import patient_rows, require_downed_victim, require_npc_target
from app.rounds.cast import CastMember, cast_of, find_reachable, label_of, labels_of, reaches, standing_label
from app.rounds.errors import ActionTargetError
from app.rounds.happenings import move_npc, npc_moves
from app.rounds.moves import to_people
from app.rounds.narration_request import is_seen
from app.rounds.narrator import HappeningNote, PersonState
from app.rounds.npc_attacks import targets_of
from app.tables.models import NpcStatus, TableNpc
from tests import test_table_map as map_tables
from tests.narration_model import asset_body
from tests.sheets import make_sheet
from tests.test_map_actions import going, play
from tests.test_table_items import FRIEND, SCENARIOS_URL, events_of, post, table_url
from tests.test_table_map import open_duo, put_at, the_map
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore

OPENING = '성문 앞이다. 노인이 지나가고, 광장에서 대장장이의 망치 소리가 들린다.'
NPC_SHEET = make_sheet(max_hp=6)


@pytest.fixture
async def people(client: AsyncClient, me: dict, lore: dict) -> dict:
    """같은 로어북에 인물 셋(경비대장, 대장장이, 은자), 사건 하나(교대), 맵 밖의 장소(지하 감옥)를 더한다."""
    url = f'{map_tables.LOREBOOKS_URL}/{lore["lorebook"]["id"]}/entries'

    async def entry(name: str, kind: str, keywords: list[str]) -> dict:
        return await post(client, url, me, name=name, keywords=keywords, content=f'{name}의 설명', kind=kind)

    return {
        **lore,
        'captain': await entry('알베르트', 'person', ['경비', '경비대장']),
        'smith': await entry('한스', 'person', ['대장장이']),
        'hermit': await entry('은자', 'person', ['노인']),
        'shift': await entry('교대', 'event', []),
        'dungeon': await entry('지하 감옥', 'place', []),
    }


def placing(person: dict, place: dict) -> dict:
    return {'entry_id': person['id'], 'place_id': place['id']}


def standing(people: dict) -> list[dict]:
    """경비대장은 성문에, 대장장이는 광장에 있다. 은자는 자리가 없다."""
    return [placing(people['captain'], people['gate']), placing(people['smith'], people['square'])]


def moving_npc(person: dict, to: dict) -> dict:
    return {'kind': 'move_npc', 'npc': person['id'], 'to_place': to['id']}


def shift(people: dict, *effects: dict) -> dict:
    """광장에 닿으면 일어나는 교대."""
    when = [{'kind': 'reach_place', 'target': people['square']['id']}]
    return {'entry_id': people['shift']['id'], 'when': when, 'effects': list(effects)}


async def draft(client: AsyncClient, me: dict, people: dict, **fields) -> dict:
    """인물의 자리를 적은 시나리오. 게시하지 않았다. 맵은 the_map 이다."""
    rulebook = await post(client, map_tables.RULEBOOKS_URL, me, title='룰북')
    body = {
        'title': '성의 모험',
        'rulebook_id': rulebook['id'],
        'openings': [OPENING],
        'default_sheet': map_tables.SHEET,
        'default_npc_sheet': NPC_SHEET,
        'lorebook_ids': [people['lorebook']['id']],
        **the_map(people),
        'npc_places': standing(people),
        **fields,
    }
    return await post(client, SCENARIOS_URL, me, **body)


async def publish(client: AsyncClient, me: dict, scenario: dict):
    return await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)


async def start(client: AsyncClient, me: dict, friend: dict, people: dict, **fields) -> dict:
    """인물의 자리를 적은 판으로 둘이 앉아 시작한 테이블."""
    scenario = {
        **the_map(people),
        'openings': [OPENING],
        'default_npc_sheet': NPC_SHEET,
        'npc_places': standing(people),
        **fields,
    }
    table = await open_duo(client, me, friend, people, **scenario)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


async def cast(client: AsyncClient, headers: dict, table: dict) -> list[tuple[str, str | None]]:
    """이번 장면의 인물들을 (부르는 이름, 있는 장소)로."""
    response = await client.get(table_url(table, '/rounds/current/people'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return [(person['name'], person['place_id']) for person in response.json()['people']]


async def place_of_npc(session: AsyncSession, table: dict, person: dict) -> uuid.UUID | None:
    query = select(TableNpc.place_id).where(
        TableNpc.table_id == uuid.UUID(table['id']), TableNpc.entry_id == uuid.UUID(person['id'])
    )
    return await session.scalar(query.execution_options(populate_existing=True))


def punch(person: dict) -> dict:
    return {'kind': 'check', 'ability': 'str', 'difficulty': 'medium', 'harm': 'moderate', 'npc': person['id']}


async def declare(client: AsyncClient, headers: dict, table: dict, action: dict):
    body = {'content': '친다.', 'action': action}
    return await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=headers)


# --- 시나리오 ---


async def test_npc_places_are_saved_and_published(client: AsyncClient, me: dict, people: dict):
    scenario = await draft(client, me, people)

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert scenario['npc_places'] == standing(people)
    published = read_snapshot(response.json()['snapshot'])
    assert [(place.entry_id, place.place_id) for place in published.npc_places] == [
        (uuid.UUID(people['captain']['id']), uuid.UUID(people['gate']['id'])),
        (uuid.UUID(people['smith']['id']), uuid.UUID(people['square']['id'])),
    ]


async def test_one_person_has_one_place(client: AsyncClient, me: dict, people: dict):
    twice = [placing(people['captain'], people['gate']), placing(people['captain'], people['square'])]
    body = {'title': '성의 모험', 'npc_places': twice}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_npc_places_are_replaced_and_cleared(client: AsyncClient, me: dict, people: dict):
    scenario = await draft(client, me, people)
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    moved = await client.patch(url, json={'npc_places': [placing(people['hermit'], people['tower'])]}, headers=me)
    cleared = await client.patch(url, json={'npc_places': []}, headers=me)

    assert moved.json()['npc_places'] == [placing(people['hermit'], people['tower'])]
    assert cleared.json()['npc_places'] == []


@pytest.mark.parametrize(
    ('case', 'problem'),
    [
        ('entry-missing', 'npc_place_not_person'),
        ('not-person', 'npc_place_not_person'),
        ('off-map', 'npc_place_off_map'),
        ('no-map', 'npc_place_off_map'),
    ],
)
async def test_a_place_must_be_a_person_on_the_map(
    client: AsyncClient, me: dict, people: dict, case: str, problem: str
):
    nowhere = {'id': str(uuid.uuid4())}
    places = {
        'entry-missing': [placing(nowhere, people['gate'])],
        'not-person': [placing(people['potion'], people['gate'])],
        'off-map': [placing(people['captain'], people['dungeon'])],
        'no-map': [placing(people['captain'], people['gate'])],
    }
    no_map = {'start_place': None, 'routes': [], 'landmarks': []} if case == 'no-map' else {}
    scenario = await draft(client, me, people, npc_places=places[case], **no_map)

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == [problem]


async def test_a_happening_moves_only_a_person(client: AsyncClient, me: dict, people: dict):
    moving_a_potion = shift(people, moving_npc(people['potion'], people['tower']))
    scenario = await draft(client, me, people, happenings=[moving_a_potion])

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['happening_npc_not_person']


async def test_a_happening_that_moves_a_person_is_saved(client: AsyncClient, me: dict, people: dict):
    rule = shift(people, moving_npc(people['captain'], people['square']))
    scenario = await draft(client, me, people, happenings=[rule])

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert scenario['happenings'][0]['effects'] == [moving_npc(people['captain'], people['square'])]
    (effect,) = read_snapshot(response.json()['snapshot']).happenings[0].effects
    assert (effect.kind, effect.npc, effect.from_place) == (
        HappeningEffectKind.MOVE_NPC,
        uuid.UUID(people['captain']['id']),
        None,
    )


async def test_moving_a_person_takes_no_starting_place(client: AsyncClient, me: dict, people: dict):
    effect = {**moving_npc(people['captain'], people['square']), 'from_place': people['gate']['id']}
    body = {'title': '성의 모험', 'happenings': [shift(people, effect)]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_snapshot_refuses_a_place_that_points_wrong(client: AsyncClient, me: dict, people: dict):
    scenario = await draft(client, me, people, happenings=[shift(people, moving_npc(people['smith'], people['gate']))])
    document = (await publish(client, me, scenario)).json()['snapshot']
    gate, potion = people['gate']['id'], people['potion']['id']
    broken = {
        'not-person': {**document, 'npc_places': [{'entry_id': potion, 'place_id': gate}]},
        'not-place': {**document, 'npc_places': [{'entry_id': people['captain']['id'], 'place_id': potion}]},
        'no-map': {**document, 'start_place': None, 'routes': [], 'landmarks': [], 'happenings': []},
        'moves-a-thing': {
            **document,
            'happenings': [
                {**document['happenings'][0], 'effects': [{'kind': 'move_npc', 'npc': potion, 'to_place': gate}]}
            ],
        },
    }

    for broken_document in broken.values():
        with pytest.raises(ValidationError):
            Snapshot.model_validate(broken_document)
    Snapshot.model_validate(document)


def test_an_old_snapshot_reads_as_no_places():
    document = {'format': 49}

    upgraded = upgrade_from_49(document)

    assert (upgraded['format'], upgraded['npc_places']) == (50, [])
    assert 'npc_places' not in document
    assert UPGRADES[49] is upgrade_from_49


# --- 장면 ---


async def test_a_placed_person_starts_at_the_place(
    client: AsyncClient, me: dict, friend: dict, people: dict, session: AsyncSession
):
    table = await start(client, me, friend, people)

    assert await place_of_npc(session, table, people['captain']) == uuid.UUID(people['gate']['id'])
    assert await place_of_npc(session, table, people['smith']) == uuid.UUID(people['square']['id'])
    assert await place_of_npc(session, table, people['hermit']) is None


async def test_the_scene_has_the_people_where_the_party_stands(
    client: AsyncClient, me: dict, friend: dict, people: dict
):
    table = await start(client, me, friend, people)

    # 경비대장은 스타팅에 나오지 않았어도 성문에 있어 든다. 진짜 이름 대신 가장 긴 키워드로 부른다.
    # 대장장이는 스타팅에 나왔어도 아무도 광장에 없어 들지 않는다. 은자는 자리가 없어 글로 든다
    assert await cast(client, me, table) == [('경비대장', people['gate']['id']), ('노인', None)]


async def test_standing_somewhere_brings_the_people_there(
    client: AsyncClient, me: dict, friend: dict, people: dict, session: AsyncSession
):
    table = await start(client, me, friend, people)

    await put_at(session, table, FRIEND, people['square'])

    # 대장장이는 스타팅에 나와 그 호칭으로 부른다
    assert await cast(client, me, table) == [
        ('경비대장', people['gate']['id']),
        ('대장장이', people['square']['id']),
        ('노인', None),
    ]


async def test_only_one_standing_there_reaches_a_placed_person(
    client: AsyncClient, me: dict, friend: dict, people: dict, session: AsyncSession
):
    table = await start(client, me, friend, people)
    await put_at(session, table, FRIEND, people['square'])

    elsewhere = await declare(client, me, table, punch(people['smith']))
    there = await declare(client, friend, table, punch(people['smith']))

    assert elsewhere.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert elsewhere.json() == {'detail': 'action.npc 가 이번 장면의 인물이 아니거나 다른 장소에 있습니다.'}
    assert there.status_code == status.HTTP_200_OK, there.text


async def test_anyone_reaches_an_unplaced_person(client: AsyncClient, me: dict, friend: dict, people: dict, session):
    table = await start(client, me, friend, people)
    await put_at(session, table, FRIEND, people['square'])

    response = await declare(client, friend, table, punch(people['hermit']))

    assert response.status_code == status.HTTP_200_OK, response.text


async def test_the_narrator_hears_where_the_people_are(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, people: dict, narrated
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    table = await start(client, me, friend, people)

    await play(client, me, friend, table, narrated)

    (request,) = narrator.requests
    assert request.people == [
        PersonState(name='경비대장', condition='멀쩡함', place='성문'),
        PersonState(name='노인', condition='멀쩡함'),
    ]


# --- 사건 ---


async def test_a_happening_moves_a_person_and_the_party_sees_it(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, people: dict, session: AsyncSession, narrated
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    # 경비대장은 광장으로, 은자는 아무도 없는 탑으로 간다
    rule = shift(people, moving_npc(people['captain'], people['square']), moving_npc(people['hermit'], people['tower']))
    table = await start(client, me, friend, people, happenings=[rule])

    await play(client, me, friend, table, narrated, mine=going(people['square']))

    assert await place_of_npc(session, table, people['captain']) == uuid.UUID(people['square']['id'])
    assert await place_of_npc(session, table, people['hermit']) == uuid.UUID(people['tower']['id'])
    # 경비대장이 떠난 성문에도 닿은 광장에도 일행이 있다. 은자는 아무도 없는 곳에서 아무도 없는 곳으로 갔다
    (request,) = narrator.requests
    assert request.happenings == [HappeningNote(name='교대', moved=['경비대장 → 광장'])]
    # 인물이 옮긴 것은 이벤트에 싣지 않는다
    (occurred,) = await events_of(client, me, table, 'happening_occurred')
    assert occurred['payload']['moves'] == []
    assert len(await events_of(client, me, table, 'character_moved')) == 1
    # 은자는 이제 자리가 있다. 글에 나와도 아무도 없는 탑에 있어 장면에 들지 않는다
    assert await cast(client, me, table) == [('경비대장', people['square']['id']), ('대장장이', people['square']['id'])]


# --- 작은 함수 ---


def entry(name: str, keywords: list[str]) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), name=name, keywords=keywords, true_names=[], kind='person')


def npc(entry_id: uuid.UUID, place: uuid.UUID | None, status_: str = NpcStatus.ALIVE) -> TableNpc:
    return TableNpc(
        entry_id=entry_id,
        place_id=place,
        status=status_,
        hp=6,
        max_hp=6,
        named_round=None,
        attitude='neutral',
        injuries=[],
    )


def member_at(place: uuid.UUID | None) -> SimpleNamespace:
    return SimpleNamespace(user_id=uuid.uuid4(), sheet=SimpleNamespace(place_id=place, hp=10, died_at=None))


GATE = uuid.uuid4()
SQUARE = uuid.uuid4()


def test_a_person_standing_unmentioned_is_called_by_the_longest_keyword():
    assert standing_label(entry('알베르트', ['대장', '경비대장', ' '])) == '경비대장'
    assert standing_label(entry('은자', [])) == '은자'
    assert standing_label(entry('은자', [' '])) == '은자'


def test_a_person_in_the_text_is_called_as_the_text_calls_them():
    shade = entry('유령', ['그림자', '검은 그림자'])
    state = npc(shade.id, GATE)

    # 글에 나온 호칭이 먼저다. 글에 없으면 가장 긴 키워드다
    assert label_of(shade, '그림자가 흔들린다.', state) == '그림자'
    assert label_of(shade, '바람이 분다.', state) == '검은 그림자'


def test_the_scene_picks_placed_people_by_place_and_others_by_mention():
    captain, smith, hermit, ghost = (
        entry('알베르트', ['경비대장']),
        entry('한스', ['대장장이']),
        entry('은자', ['노인']),
        entry('유령', ['그림자']),
    )
    snapshot = SimpleNamespace(
        lorebooks=[SimpleNamespace(entries=[captain, smith, hermit, ghost])], npc_sheets=[], monsters=[]
    )
    states = [npc(captain.id, GATE), npc(smith.id, SQUARE), npc(hermit.id, None), npc(ghost.id, None)]
    scene = '대장장이가 부른다. 노인이 웃는다.'

    picked = cast_of(snapshot, scene, states, {GATE})

    assert [(person.entry_id, person.name) for person in picked] == [(captain.id, '경비대장'), (hermit.id, '노인')]
    assert cast_of(snapshot, scene, states) == [picked[1]]
    # 상태가 없는 인물은 들지 않는다
    assert labels_of(snapshot, scene, states[:3]) == {captain.id: '경비대장', smith.id: '대장장이', hermit.id: '노인'}
    assert labels_of(snapshot, scene, states) == {
        captain.id: '경비대장',
        smith.id: '대장장이',
        hermit.id: '노인',
        ghost.id: '그림자',
    }


def test_a_named_person_is_called_by_the_true_name():
    captain = entry('알베르트', ['경비대장'])
    snapshot = SimpleNamespace(lorebooks=[SimpleNamespace(entries=[captain])], npc_sheets=[], monsters=[])
    state = npc(captain.id, GATE)
    state.named_round = 2

    assert [person.name for person in cast_of(snapshot, '', [state], {GATE})] == ['알베르트']


def person(place: uuid.UUID | None, status_: str = NpcStatus.ALIVE) -> CastMember:
    entry_id = uuid.uuid4()
    return CastMember(entry_id, '경비대장', npc(entry_id, place, status_))


def test_who_reaches_whom():
    placed, unplaced = person(GATE), person(None)
    here, there, nowhere = member_at(GATE), member_at(SQUARE), SimpleNamespace(sheet=None)

    assert [reaches(one, placed) for one in (here, there, nowhere)] == [True, False, False]
    assert [reaches(one, unplaced) for one in (here, there, nowhere)] == [True, True, True]
    assert find_reachable([placed], here, placed.entry_id) is placed
    assert find_reachable([placed], there, placed.entry_id) is None
    assert find_reachable([placed], here, uuid.uuid4()) is None


def test_every_way_of_aiming_at_a_person_needs_the_same_place():
    downed = person(GATE, NpcStatus.DOWNED)
    cast = [downed]
    scene = SimpleNamespace(cast=cast, monsters=[])
    there = member_at(SQUARE)
    treat = TreatAction(kind='treat', injury='bleeding', npc=downed.entry_id)
    loot = LootAction(kind='loot', npc=downed.entry_id, item=uuid.uuid4())

    for aimed in (
        lambda: require_npc_target(cast, there, downed.entry_id, None),
        lambda: patient_rows(SimpleNamespace(), there, treat, cast),
        lambda: require_downed_victim(scene, there, loot),
        lambda: trades.require_merchant(scene, there, downed.entry_id),
    ):
        with pytest.raises(ActionTargetError):
            aimed()

    here = member_at(GATE)
    require_npc_target(cast, here, downed.entry_id, None)
    assert patient_rows(SimpleNamespace(), here, treat, cast) == []
    require_downed_victim(scene, here, loot)


def test_a_placed_person_strikes_only_those_standing_there():
    here, there = member_at(GATE), member_at(SQUARE)
    judging = SimpleNamespace(downed_at_start=frozenset(), table=SimpleNamespace(members=[here, there]))

    assert targets_of(judging, person(GATE)) == [here]
    assert targets_of(judging, person(None)) == [here, there]


def effect_to(place: uuid.UUID, npc_id: uuid.UUID) -> HappeningEffectSnapshot:
    return HappeningEffectSnapshot(kind=HappeningEffectKind.MOVE_NPC, to_place=place, npc=npc_id)


def test_moving_a_person():
    walker, corpse, already, newcomer = (
        npc(uuid.uuid4(), GATE),
        npc(uuid.uuid4(), GATE, NpcStatus.DEAD),
        npc(uuid.uuid4(), SQUARE),
        npc(uuid.uuid4(), None),
    )

    assert move_npc(walker, effect_to(SQUARE, walker.entry_id)) == {
        'entry_id': str(walker.entry_id),
        'from': str(GATE),
        'to': str(SQUARE),
    }
    assert walker.place_id == SQUARE
    # 죽은 인물은 남고, 이미 그곳에 있는 인물은 옮겼다고 적지 않는다. 상태가 없는 인물은 옮길 것이 없다
    assert move_npc(corpse, effect_to(SQUARE, corpse.entry_id)) is None
    assert corpse.place_id == GATE
    assert move_npc(already, effect_to(SQUARE, already.entry_id)) is None
    assert move_npc(None, effect_to(SQUARE, uuid.uuid4())) is None
    # 자리가 없던 인물은 자리가 생긴다
    assert move_npc(newcomer, effect_to(GATE, newcomer.entry_id))['from'] is None
    assert newcomer.place_id == GATE


def test_a_happening_moves_people_in_order_and_skips_the_rest():
    first, second = npc(uuid.uuid4(), GATE), npc(uuid.uuid4(), GATE)
    rule = SimpleNamespace(
        effects=[
            effect_to(SQUARE, second.entry_id),
            HappeningEffectSnapshot(kind=HappeningEffectKind.MOVE, to_place=SQUARE),
            effect_to(SQUARE, first.entry_id),
        ]
    )

    moved = npc_moves([first, second], rule)

    assert [move['entry_id'] for move in moved] == [str(second.entry_id), str(first.entry_id)]


def test_the_party_sees_a_person_leave_or_arrive():
    elsewhere = str(uuid.uuid4())

    assert is_seen({'from': str(GATE), 'to': elsewhere}, {GATE}) is True
    assert is_seen({'from': elsewhere, 'to': str(GATE)}, {GATE}) is True
    assert is_seen({'from': None, 'to': elsewhere}, {GATE}) is False
    assert is_seen({'from': elsewhere, 'to': elsewhere}, {GATE}) is False


def test_the_people_lines_tell_the_place():
    placed = PersonState('경비대장', '멀쩡함', place='성문')

    assert prompt.person_line(placed) == '- 경비대장 [성문]: 멀쩡함'
    assert prompt.people_lines([placed]) == [
        prompt.PEOPLE_TITLE,
        prompt.PEOPLE_NOTE,
        prompt.PEOPLE_PLACE_NOTE,
        '- 경비대장 [성문]: 멀쩡함',
        '',
    ]
    assert prompt.PEOPLE_PLACE_NOTE not in prompt.people_lines([PersonState('노인', '멀쩡함')])


def test_to_people_names_the_place_of_a_placed_person():
    placed, unplaced = person(GATE), person(None)

    states = to_people([placed, unplaced], SimpleNamespace(injuries=[]), {GATE: '성문'})

    assert [state.place for state in states] == ['성문', None]
