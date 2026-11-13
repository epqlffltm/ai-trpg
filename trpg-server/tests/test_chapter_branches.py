# trpg-server/tests/test_chapter_branches.py

"""
장의 갈림길(#289, app/tables/chapters.py, app/rounds/chapters.py)을 검증한다.

맵과 픽스처는 tests/test_happenings.py 의 것이다. 방장(기사)과 함께 앉는 사람(약사)이 성문(시작)에 선다.
성문-광장 큰길, 광장→지하실 숨긴 길, 성문-숲 안개 길, 오두막-숲 안개 길, 탑은 명소다.
장은 넷이다. 도착(처음), 마을(도착 다음, 광장에 닿으면, 탑을 연다), 들(도착 다음, 숲에 닿으면, 오두막을 연다),
끝(마을이나 들 다음, 성문에 서면). 마을과 들이 갈림길이고 끝에서 합친다.

보는 것.
  - 갈림길: 지금 장 다음에 갈 수 있는 장들의 조건을 목록의 차례로 맞춰 처음 맞는 장으로 간다. 함께 맞으면 앞쪽이다
  - 고르지 않은 가지: 그 장으로는 다시 가지 못하고, 그 장이 여는 장소는 닫힌 채다. chapter_at_least 도 채워지지 않는다
  - 합류: 어느 가지로 왔든 끝으로 넘어간다
  - 몇째 장(number)은 지나온 장의 수, 몇 개 중(total)은 가장 긴 길의 장의 수다
  - 모양: 첫 장에는 after 를 적지 않고, after 에는 목록에서 앞의 장만 한 번씩 적는다. 비우면 빈 목록이다
  - 작은 함수: 앞의 장, 가장 긴 길, 지나온 장(적기 전에 시작한 테이블), 갈 수 있는 장, 닫힌 것
"""

import uuid
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import status
from httpx import AsyncClient

from app.assets.scenarios.snapshot import ChapterSnapshot, Snapshot
from app.tables import chapters as table_chapters
from app.tables.models import GameTable
from tests import test_happenings as happening_tests
from tests.test_happenings import draft, reach, start
from tests.test_map_actions import going, play
from tests.test_table_items import SCENARIOS_URL, events_of, read_table
from tests.test_table_map import known_places

pytestmark = pytest.mark.usefixtures('clean_tables')

me = happening_tests.me
friend = happening_tests.friend
lore = happening_tests.lore
more = happening_tests.more


def branching(more: dict) -> list[dict]:
    """도착, 마을(광장, 탑을 연다), 들(숲, 오두막을 연다), 끝(마을이나 들 다음, 성문)."""
    return [
        {'id': 'arrival', 'name': '도착'},
        {
            'id': 'town',
            'name': '마을',
            'after': ['arrival'],
            'when': [reach(more['square'])],
            'opens': {'places': [more['tower']['id']]},
        },
        {
            'id': 'wild',
            'name': '들',
            'after': ['arrival'],
            'when': [reach(more['forest'])],
            'opens': {'places': [more['hut']['id']]},
        },
        {'id': 'end', 'name': '끝', 'after': ['town', 'wild'], 'when': [reach(more['gate'])]},
    ]


def rescue_after(more: dict, chapter_id: str) -> dict:
    """진행 중으로 시작하고 그 장을 지나오면 이루는 왕녀 구출."""
    condition = {'kind': 'chapter_at_least', 'chapter': chapter_id}
    return {'entry_id': more['rescue']['id'], 'start': 'active', 'conditions': [condition]}


async def test_the_branch_whose_condition_is_met_is_taken(
    client: AsyncClient, me: dict, friend: dict, more: dict, narrated
):
    table = await start(client, me, friend, more, [], chapters=branching(more))
    first = await read_table(client, me, table)

    await play(client, me, friend, table, narrated, mine=going(more['square']))
    seen = await read_table(client, me, table)

    assert first['chapter'] == {'id': 'arrival', 'name': '도착', 'number': 1, 'total': 3, 'entered_round': None}
    assert seen['chapter'] == {'id': 'town', 'name': '마을', 'number': 2, 'total': 3, 'entered_round': 1}
    (changed,) = await events_of(client, me, table, 'chapter_changed')
    assert changed['payload']['to'] == {'id': 'town', 'name': '마을'}
    assert changed['payload']['number'] == 2
    assert '탑' in known_places(seen)


async def test_when_both_branches_are_met_the_earlier_one_wins(
    client: AsyncClient, me: dict, friend: dict, more: dict, narrated
):
    table = await start(client, me, friend, more, [], chapters=branching(more))

    # 기사는 광장(마을), 약사는 숲(들)에 간다. 둘 다 맞으면 목록의 앞쪽인 마을이다
    await play(client, me, friend, table, narrated, mine=going(more['square']), theirs=going(more['forest']))

    assert (await read_table(client, me, table))['chapter']['id'] == 'town'


async def test_the_branch_not_taken_stays_closed(client: AsyncClient, me: dict, friend: dict, more: dict, narrated):
    table = await start(client, me, friend, more, [], chapters=branching(more), quests=[rescue_after(more, 'wild')])

    await play(client, me, friend, table, narrated, mine=going(more['square']), theirs=going(more['forest']))
    # 마을로 갈렸다. 그 뒤 약사가 숲에 서 있어도 들로는 가지 않는다(끝의 조건은 성문이라 아직이다)
    await play(client, me, friend, table, narrated)
    seen = await read_table(client, me, table)

    assert seen['chapter']['id'] == 'town'
    assert '오두막' not in known_places(seen)
    assert seen['quests'][0]['status'] == 'active'
    assert len(await events_of(client, me, table, 'chapter_changed')) == 1


async def test_both_branches_meet_again(client: AsyncClient, me: dict, friend: dict, more: dict, narrated):
    table = await start(client, me, friend, more, [], chapters=branching(more), quests=[rescue_after(more, 'wild')])

    await play(client, me, friend, table, narrated, mine=going(more['forest']), theirs=going(more['forest']))
    wild = await read_table(client, me, table)
    await play(client, me, friend, table, narrated, mine=going(more['gate']))
    end = await read_table(client, me, table)

    assert (wild['chapter']['id'], wild['chapter']['number']) == ('wild', 2)
    assert '오두막' in known_places(wild) and '탑' not in known_places(wild)
    assert end['chapter'] == {'id': 'end', 'name': '끝', 'number': 3, 'total': 3, 'entered_round': 2}
    # 들을 지나왔으니 들을 기다리던 퀘스트는 이룬다(장을 넘긴 다음 라운드에 본다)
    assert end['quests'][0]['status'] == 'succeeded'


# --- 모양 ---


async def save_chapters(client: AsyncClient, me: dict, more: dict, chapters: list[dict]):
    scenario = await draft(client, me, more, [])
    return await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'chapters': chapters}, headers=me)


async def test_branches_are_saved_and_an_empty_after_is_empty(client: AsyncClient, me: dict, more: dict):
    linear = [{'id': 'arrival', 'name': '도착'}, {'id': 'next', 'name': '다음', 'when': [reach(more['square'])]}]

    branched = await save_chapters(client, me, more, branching(more))
    plain = await save_chapters(client, me, more, linear)

    assert branched.status_code == status.HTTP_200_OK, branched.text
    assert [chapter['after'] for chapter in branched.json()['chapters']] == [
        [],
        ['arrival'],
        ['arrival'],
        ['town', 'wild'],
    ]
    assert plain.json()['chapters'][1]['after'] == []


@pytest.mark.parametrize('case', ['first', 'later', 'unknown', 'self', 'twice'])
async def test_a_misshaped_branch_is_refused(client: AsyncClient, me: dict, more: dict, case: str):
    chapters = branching(more)
    if case == 'first':
        chapters[0]['after'] = ['town']
    elif case == 'later':
        chapters[1]['after'] = ['wild']
    elif case == 'unknown':
        chapters[3]['after'] = ['nowhere']
    elif case == 'self':
        chapters[3]['after'] = ['end']
    else:
        chapters[3]['after'] = ['town', 'town']

    response = await save_chapters(client, me, more, chapters)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text


# --- 작은 함수 ---


def chapter(key: str, after: list[str] | None = None) -> ChapterSnapshot:
    return ChapterSnapshot(id=key, name=key, after=after or [])


def test_predecessors_default_to_the_chapter_just_before():
    ids = ['a', 'b', 'c']

    assert table_chapters.predecessors(ids, 0, []) == []
    assert table_chapters.predecessors(ids, 2, []) == ['b']
    assert table_chapters.predecessors(ids, 2, ['a']) == ['a']


def test_the_longest_route_counts_chapters_on_it():
    linear = cast(Snapshot, SimpleNamespace(chapters=[chapter('a'), chapter('b'), chapter('c')]))
    forked = cast(
        Snapshot,
        SimpleNamespace(
            chapters=[
                chapter('a'),
                chapter('b', ['a']),
                chapter('c', ['a']),
                chapter('d', ['c']),
                chapter('e', ['b', 'd']),
            ]
        ),
    )

    assert table_chapters.longest(linear) == 3
    assert table_chapters.longest(forked) == 4
    assert table_chapters.longest(cast(Snapshot, SimpleNamespace(chapters=[]))) == 0


def test_chapters_passed_before_the_path_was_kept_are_read_in_order():
    content = {'chapters': [{'id': 'a'}, {'id': 'b'}, {'id': 'c'}]}
    old = cast(GameTable, SimpleNamespace(chapter_id='b', chapter_path=[], content=content))
    new = cast(GameTable, SimpleNamespace(chapter_id='c', chapter_path=['a', 'c'], content=content))

    assert table_chapters.passed(old) == ['a', 'b']
    assert (table_chapters.passed(new), table_chapters.number_of(new)) == (['a', 'c'], 2)
    assert table_chapters.at_least(new, 'a') and not table_chapters.at_least(new, 'b')


def test_the_candidates_follow_the_current_chapter_in_order():
    snapshot = cast(
        Snapshot,
        SimpleNamespace(chapters=[chapter('a'), chapter('b', ['a']), chapter('c', ['a']), chapter('d', ['b', 'c'])]),
    )
    at = cast(GameTable, SimpleNamespace(chapter_id='a'))
    on_c = cast(GameTable, SimpleNamespace(chapter_id='c'))
    last = cast(GameTable, SimpleNamespace(chapter_id='d'))

    assert [one.id for one in table_chapters.candidates(at, snapshot)] == ['b', 'c']
    assert [one.id for one in table_chapters.candidates(on_c, snapshot)] == ['d']
    assert table_chapters.candidates(last, snapshot) == []


def test_what_an_untaken_branch_opens_stays_locked():
    tower, hut, cave = (uuid.uuid4() for _ in range(3))
    content = {
        'chapters': [
            {'id': 'a'},
            {'id': 'b', 'after': ['a'], 'opens': {'places': [str(tower)]}},
            {'id': 'c', 'after': ['a'], 'opens': {'places': [str(hut)]}},
            {'id': 'd', 'after': ['b', 'c'], 'opens': {'quests': [str(cave)]}},
        ]
    }
    table = cast(GameTable, SimpleNamespace(chapter_id='b', chapter_path=['a', 'b'], content=content))

    assert table_chapters.locked_ids(table) == frozenset({hut, cave})
