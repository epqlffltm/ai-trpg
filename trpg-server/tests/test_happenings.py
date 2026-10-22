# trpg-server/tests/test_happenings.py

"""
판의 사건 규칙(#367, app/rounds/happenings.py)을 검증한다. 방장이 캐릭터를 손으로 옮기던 것을 대신한다.

맵과 픽스처는 tests/test_table_map.py 의 것이다. 방장(기사)과 함께 앉는 사람(약사), 성문(시작)-광장 큰길,
광장→지하실 숨긴 길, 성문-숲 안개 길, 탑은 명소. 여기에 사건 항목 셋과 맵 밖의 장소(지하 감옥)를 더한다.

보는 것.
  - 시나리오: 사건 규칙을 저장하고 판에 굳힌다. 잘못 둔 것은 422, 게시할 수 없는 것은 409 의 문제다.
    옛 판은 사건 규칙이 없는 것으로 읽는다.
  - 라운드: 조건이 채워지면 한 번 일어나 옮긴다(그 장소에 선 사람이나 모두). 쓰러진 사람도 옮겨지고 죽은 사람은 남는다.
    이벤트는 사건 뒤에 옮긴 사람마다 character_moved 다. 퀘스트를 본 뒤라 같은 라운드의 성공으로 일어난다.
  - 서술: 그 라운드에 일어난 사건이 [일어난 사건]으로 간다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_43
from app.rounds import prompt
from app.rounds.narrator import HappeningNote
from tests import test_table_map as map_tables
from tests.narration_model import asset_body
from tests.test_map_actions import going, play
from tests.test_table_items import FRIEND, ME, SCENARIOS_URL, events_of, kill, post, read_table, table_url
from tests.test_table_map import open_duo, place_of, put_at, the_map
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore


@pytest.fixture
async def more(client: AsyncClient, me: dict, lore: dict) -> dict:
    """같은 로어북에 사건 항목 셋(함정, 휩쓸림, 왕녀 구출)과 맵 밖의 장소(지하 감옥)를 더한다."""
    url = f'{map_tables.LOREBOOKS_URL}/{lore["lorebook"]["id"]}/entries'

    async def entry(name: str, kind: str) -> dict:
        return await post(client, url, me, name=name, keywords=[], content=f'{name}의 설명', kind=kind)

    return {
        **lore,
        'trap': await entry('함정', 'event'),
        'storm': await entry('휩쓸림', 'event'),
        'rescue': await entry('왕녀 구출', 'event'),
        'dungeon': await entry('지하 감옥', 'place'),
    }


def reach(place: dict) -> dict:
    """그 장소에 닿기의 조건."""
    return {'kind': 'reach_place', 'target': place['id']}


def moving(to: dict, from_: dict | None = None) -> dict:
    """옮기기의 효과. from_ 이 없으면 모두다."""
    effect = {'kind': 'move', 'to_place': to['id']}
    return effect if from_ is None else {**effect, 'from_place': from_['id']}


def happening(entry: dict, when: list[dict], effects: list[dict], **fields) -> dict:
    return {'entry_id': entry['id'], 'when': when, 'effects': effects, **fields}


def trap(more: dict) -> dict:
    """광장에 닿으면 광장에 선 사람이 숨긴 지하실로 떨어진다."""
    return happening(more['trap'], [reach(more['square'])], [moving(more['cellar'], more['square'])])


async def start(client: AsyncClient, me: dict, friend: dict, more: dict, happenings: list[dict], **fields) -> dict:
    """그 사건 규칙들로 둘이 앉아 시작한 테이블. 맵은 the_map 이다."""
    table = await open_duo(client, me, friend, more, **the_map(more), happenings=happenings, **fields)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


async def draft(client: AsyncClient, me: dict, more: dict, happenings: list[dict]) -> dict:
    """그 사건 규칙들을 적은 시나리오. 게시하지 않았다."""
    rulebook = await post(client, map_tables.RULEBOOKS_URL, me, title='룰북')
    body = {
        'title': '성의 모험',
        'rulebook_id': rulebook['id'],
        'openings': ['성문 앞이다.'],
        'default_sheet': map_tables.SHEET,
        'lorebook_ids': [more['lorebook']['id']],
        **the_map(more),
        'happenings': happenings,
    }
    return await post(client, SCENARIOS_URL, me, **body)


async def publish(client: AsyncClient, me: dict, scenario: dict):
    return await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)


# --- 시나리오 ---


async def test_happenings_are_saved_and_published(client: AsyncClient, me: dict, more: dict):
    scenario = await draft(client, me, more, [trap(more)])

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert scenario['happenings'] == [
        {
            'entry_id': more['trap']['id'],
            'when': [{'kind': 'reach_place', 'target': more['square']['id'], 'count': 1, 'consume': False}],
            'match': 'all',
            'effects': [{'kind': 'move', 'to_place': more['cellar']['id'], 'from_place': more['square']['id']}],
        }
    ]
    (published,) = read_snapshot(response.json()['snapshot']).happenings
    assert (published.entry_id, published.effects[0].to_place) == (
        uuid.UUID(more['trap']['id']),
        uuid.UUID(more['cellar']['id']),
    )


@pytest.mark.parametrize('case', ['no-condition', 'no-effect', 'consume', 'same-place', 'twice'])
async def test_a_misplaced_happening_is_refused(client: AsyncClient, me: dict, more: dict, case: str):
    potion = {'kind': 'hold_item', 'target': more['potion']['id'], 'consume': True}
    rules = {
        'no-condition': [happening(more['trap'], [], [moving(more['cellar'])])],
        'no-effect': [happening(more['trap'], [reach(more['square'])], [])],
        'consume': [happening(more['trap'], [potion], [moving(more['cellar'])])],
        'same-place': [happening(more['trap'], [reach(more['square'])], [moving(more['square'], more['square'])])],
        'twice': [trap(more), trap(more)],
    }
    body = {'title': '성의 모험', 'happenings': rules[case]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    ('case', 'problem'),
    [
        ('entry-missing', 'happening_entry_missing'),
        ('not-event', 'happening_not_event'),
        ('condition-missing', 'happening_condition_missing'),
        ('condition-invalid', 'happening_condition_invalid'),
        ('condition-impossible', 'happening_condition_impossible'),
        ('off-map', 'happening_place_off_map'),
    ],
)
async def test_a_happening_must_point_at_something_possible(
    client: AsyncClient, me: dict, more: dict, case: str, problem: str
):
    nowhere = {'id': str(uuid.uuid4())}
    rules = {
        'entry-missing': happening(nowhere, [reach(more['square'])], [moving(more['cellar'])]),
        'not-event': happening(more['potion'], [reach(more['square'])], [moving(more['cellar'])]),
        'condition-missing': happening(more['trap'], [reach(nowhere)], [moving(more['cellar'])]),
        'condition-invalid': happening(more['trap'], [reach(more['potion'])], [moving(more['cellar'])]),
        # 맵에 없는 장소에는 아무도 설 수 없다
        'condition-impossible': happening(more['trap'], [reach(more['dungeon'])], [moving(more['cellar'])]),
        'off-map': happening(more['trap'], [reach(more['square'])], [moving(more['dungeon'])]),
    }
    scenario = await draft(client, me, more, [rules[case]])

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == [problem]


def test_an_old_snapshot_reads_as_no_happenings():
    document = {'format': 43, 'quests': []}

    upgraded = upgrade_from_43(document)

    assert (upgraded['format'], upgraded['happenings']) == (44, [])
    assert 'happenings' not in document
    assert UPGRADES[43] is upgrade_from_43


# --- 라운드 ---


async def test_stepping_on_the_trap_drops_those_standing_there(
    client: AsyncClient, me: dict, friend: dict, more: dict, narrated
):
    table = await start(client, me, friend, more, [trap(more)])

    await play(client, me, friend, table, narrated, mine=going(more['square']))

    # 광장에 선 기사만 숨긴 지하실로 떨어진다. 성문의 약사는 그대로다. 지하실은 이제 안다(서 본 곳)
    seen = await read_table(client, friend, table)
    assert (place_of(seen, ME), place_of(seen, FRIEND)) == (more['cellar']['id'], more['gate']['id'])
    assert '지하실' in map_tables.known_places(seen)
    (occurred,) = await events_of(client, friend, table, 'happening_occurred')
    assert occurred['actor_id'] is None
    assert occurred['payload'] == {
        'round': 1,
        'entry_id': more['trap']['id'],
        'name': '함정',
        'moves': [
            {
                'user_id': str(ME),
                'character_name': '기사',
                'from': {'entry_id': more['square']['id'], 'name': '광장'},
                'to': {'entry_id': more['cellar']['id'], 'name': '지하실'},
            }
        ],
    }
    walked, dropped = await events_of(client, friend, table, 'character_moved')
    assert walked['payload']['to']['name'] == '광장'
    assert (dropped['caused_by_sequence'], dropped['payload']['happening']) == (
        occurred['sequence'],
        more['trap']['id'],
    )
    assert dropped['payload']['to']['name'] == '지하실'


async def test_a_happening_happens_once(
    client: AsyncClient, me: dict, friend: dict, more: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, more, [trap(more)])
    await play(client, me, friend, table, narrated, mine=going(more['square']))

    # 다시 광장에 섰다. 조건이 또 채워져도 사건은 한 번뿐이다
    await put_at(session, table, ME, more['square'])
    await play(client, me, friend, table, narrated)

    assert place_of(await read_table(client, me, table), ME) == more['square']['id']
    assert len(await events_of(client, me, table, 'happening_occurred')) == 1


async def test_everyone_is_swept_away_the_downed_too_but_not_the_dead(
    client: AsyncClient, me: dict, friend: dict, more: dict, session: AsyncSession, narrated
):
    storm = happening(more['storm'], [reach(more['gate'])], [moving(more['tower'])])
    table = await start(client, me, friend, more, [storm])
    await kill(session, FRIEND)

    await play_alone(client, me, table, narrated)

    seen = await read_table(client, me, table)
    assert place_of(seen, ME) == more['tower']['id']
    # 죽은 캐릭터는 쓰러진 곳에 남는다
    assert place_of(seen, FRIEND) == more['gate']['id']
    (occurred,) = await events_of(client, me, table, 'happening_occurred')
    assert [move['character_name'] for move in occurred['payload']['moves']] == ['기사']


async def test_one_already_there_is_not_moved(
    client: AsyncClient, me: dict, friend: dict, more: dict, session: AsyncSession, narrated
):
    storm = happening(more['storm'], [reach(more['square'])], [moving(more['tower'])])
    table = await start(client, me, friend, more, [storm])
    await put_at(session, table, FRIEND, more['tower'])

    await play(client, me, friend, table, narrated, mine=going(more['square']))

    # 약사는 이미 탑에 있었다. 옮겼다고 적지 않는다
    (occurred,) = await events_of(client, me, table, 'happening_occurred')
    assert [move['character_name'] for move in occurred['payload']['moves']] == ['기사']
    assert len(await events_of(client, me, table, 'character_moved')) == 2


async def test_a_downed_character_is_dragged_along(
    client: AsyncClient, me: dict, friend: dict, more: dict, session: AsyncSession, narrated
):
    storm = happening(more['storm'], [reach(more['gate'])], [moving(more['tower'])])
    table = await start(client, me, friend, more, [storm])
    # 고비를 넘기고 쓰러져 있다(죽음의 굴림을 굴리지 않는다)
    query = 'UPDATE table_sheets SET hp = 0, death_successes = 3 WHERE user_id = :user_id'
    await session.execute(text(query), {'user_id': FRIEND})
    await session.commit()

    await play_alone(client, me, table, narrated)

    seen = await read_table(client, me, table)
    assert place_of(seen, ME) == place_of(seen, FRIEND) == more['tower']['id']


async def play_alone(client: AsyncClient, me: dict, table: dict, narrated) -> None:
    """나만 선언해 라운드를 닫는다(함께 앉은 사람은 쓰러졌거나 죽었다)."""
    url = table_url(table, '/rounds/current/declaration')
    declared = await client.put(url, json={'content': '둘러본다.'}, headers=me)
    assert declared.status_code == status.HTTP_200_OK, declared.text
    await narrated()


async def test_a_quest_success_sets_off_a_happening_in_the_same_round(
    client: AsyncClient, me: dict, friend: dict, more: dict, narrated
):
    rescue = {'entry_id': more['rescue']['id'], 'start': 'active', 'conditions': [reach(more['square'])]}
    linked = {'kind': 'quest_succeeded', 'target': more['rescue']['id']}
    storm = happening(more['storm'], [linked], [moving(more['tower'])])
    table = await start(client, me, friend, more, [storm], quests=[rescue])

    await play(client, me, friend, table, narrated, mine=going(more['square']))

    # 퀘스트를 본 뒤에 사건을 본다. 왕녀를 구한 그 라운드에 둘 다 탑으로 옮겨진다
    seen = await read_table(client, me, table)
    assert place_of(seen, ME) == place_of(seen, FRIEND) == more['tower']['id']
    (changed,) = await events_of(client, me, table, 'quest_changed')
    (occurred,) = await events_of(client, me, table, 'happening_occurred')
    assert changed['sequence'] < occurred['sequence']


async def test_nothing_happens_until_the_condition_is_met(
    client: AsyncClient, me: dict, friend: dict, more: dict, narrated
):
    table = await start(client, me, friend, more, [trap(more)])

    await play(client, me, friend, table, narrated)

    assert await events_of(client, me, table, 'happening_occurred') == []
    assert place_of(await read_table(client, me, table), ME) == more['gate']['id']


# --- 서술 ---


async def test_the_narrator_hears_what_happened(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, more: dict, narrated
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    table = await start(client, me, friend, more, [trap(more)])

    await play(client, me, friend, table, narrated, mine=going(more['square']))
    await play(client, me, friend, table, narrated)

    first, second = narrator.requests
    assert first.happenings == [HappeningNote(name='함정', moved=['기사 → 지하실'])]
    # 그 라운드에 일어난 것만 간다
    assert second.happenings == []


def test_the_prompt_tells_what_happened():
    lines = prompt.happening_lines([HappeningNote('함정', ['기사 → 지하실']), HappeningNote('휩쓸림')])

    assert lines == [
        prompt.HAPPENING_TITLE,
        prompt.HAPPENING_NOTE,
        '- 함정: 기사 → 지하실',
        f'- 휩쓸림: {prompt.HAPPENING_NO_MOVE}',
        '',
    ]
    assert prompt.happening_lines([]) == []
