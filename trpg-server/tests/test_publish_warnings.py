# trpg-server/tests/test_publish_warnings.py

"""
게시 점검의 알릴 것(warnings, app/assets/scenarios/publishing.py 의 find_warnings)을 검증한다. 게시를 막지 않는다.

맵과 픽스처는 tests/test_happenings.py 의 것이다. 성문(시작)-광장 큰길, 광장→지하실 숨긴 길, 성문-숲 안개 길,
오두막-숲 안개 길, 탑은 명소. 사건 항목 셋(함정, 휩쓸림, 왕녀 구출)이 있다.

보는 것.
  - chapter_condition_locked(#289): 장으로 넘어오는 조건이 기다리는 장소(서기)나 퀘스트(성공·실패)를,
    그 장의 앞에 지날 수 있는 장이 열지 않으면 알린다. 뒤의 장이 열거나, 다른 갈림길이 열거나, 그 장 자신이 열 때다
  - 앞에 지날 수 있는 장이 열거나 어느 장도 열지 않으면 알리지 않는다. 장이 없는 판도 알리지 않는다
  - 알릴 것이 있어도 게시 점검은 ready 이고 게시된다
  - quest_condition_locked, happening_condition_locked, achievement_condition_locked(#289): 조건이 갈림길 때문에
    채워질 수 없다. 모두(all)면 함께 채울 것들을 여는 장이 서로 다른 갈림길이거나, 퀘스트를 여는 장과 조건이 기다리는
    것을 여는 장이 그렇다. 하나라도(any)면 조건마다 그렇다. 퀘스트의 실패하는 조건은 보지 않는다
  - 작은 함수: 조상(ancestors)
"""

from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import status
from httpx import AsyncClient

from app.assets.scenarios.chapter_graph import ChapterLike, ancestors
from tests import test_happenings as happening_tests
from tests.test_happenings import happening, moving, publish, reach
from tests.test_scenario_chapters import chapter, draft_with
from tests.test_table_items import SCENARIOS_URL

pytestmark = pytest.mark.usefixtures('clean_tables')

me = happening_tests.me
lore = happening_tests.lore
more = happening_tests.more

LOCKED = 'chapter_condition_locked'


def succeeded(entry: dict) -> dict:
    return {'kind': 'quest_succeeded', 'target': entry['id']}


async def check(client: AsyncClient, me: dict, scenario: dict) -> dict:
    response = await client.get(f'{SCENARIOS_URL}/{scenario["id"]}/publish-check', headers=me)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def cases(more: dict) -> dict[str, list[dict]]:
    """알리는 판들. 장 이름은 도착(첫 장)과 그 뒤의 장들이다."""
    return {
        # 둘째 장이 기다리는 지하실을 셋째 장이 연다
        'later': [
            chapter('arrival', '도착'),
            chapter('below', '지하', [reach(more['cellar'])]),
            chapter('deep', '깊은 곳', [reach(more['square'])], places=[more['cellar']]),
        ],
        # 자기가 여는 오두막을 기다린다
        'itself': [
            chapter('arrival', '도착'),
            chapter('hut', '오두막', [reach(more['hut'])], places=[more['hut']]),
        ],
        # 들(도착 다음)이 연 오두막을, 다른 갈림길인 마을이 기다린다
        'other-branch': [
            chapter('arrival', '도착'),
            {**chapter('wild', '들', [reach(more['forest'])], places=[more['hut']]), 'after': ['arrival']},
            {**chapter('town', '마을', [reach(more['hut'])]), 'after': ['arrival']},
        ],
    }


@pytest.mark.parametrize('case', ['later', 'itself', 'other-branch'])
async def test_a_chapter_waiting_for_what_opens_too_late_is_warned(client: AsyncClient, me: dict, more: dict, case):
    scenario = await draft_with(client, me, more, cases(more)[case])

    checked = await check(client, me, scenario)

    assert (checked['ready'], checked['problems'], checked['warnings']) == (True, [], [LOCKED])
    assert (await publish(client, me, scenario)).status_code == status.HTTP_201_CREATED


async def test_a_chapter_waiting_for_a_quest_opened_later_is_warned(client: AsyncClient, me: dict, more: dict):
    # 지하는 왕녀 구출의 성공을 기다리는데, 그 퀘스트는 뒤의 깊은 곳이 연다
    chapters = [
        chapter('arrival', '도착'),
        chapter('below', '지하', [succeeded(more['rescue'])]),
        chapter('deep', '깊은 곳', [reach(more['square'])], quests=[more['rescue']]),
    ]
    scenario = await draft_with(client, me, more, chapters)
    rescue = {'entry_id': more['rescue']['id'], 'start': 'active', 'conditions': [reach(more['tower'])]}
    saved = await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'quests': [rescue]}, headers=me)
    assert saved.status_code == status.HTTP_200_OK, saved.text

    checked = await check(client, me, scenario)

    assert (checked['problems'], checked['warnings']) == ([], [LOCKED])


async def test_what_an_earlier_chapter_opens_is_fine(client: AsyncClient, me: dict, more: dict):
    # 들이 연 오두막을 들 다음의 끝이 기다린다. 첫 장 다음의 장은 어느 장도 열지 않은 광장을 기다린다
    chapters = [
        chapter('arrival', '도착'),
        chapter('wild', '들', [reach(more['square'])], places=[more['hut']]),
        {**chapter('end', '끝', [reach(more['hut'])]), 'after': ['wild']},
    ]
    scenario = await draft_with(client, me, more, chapters)

    assert (await check(client, me, scenario))['warnings'] == []


async def test_a_scenario_without_chapters_has_no_warnings(client: AsyncClient, me: dict, more: dict):
    scenario = await draft_with(client, me, more, [])

    assert (await check(client, me, scenario))['warnings'] == []


# --- 퀘스트, 사건, 업적 ---


def forked(more: dict) -> list[dict]:
    """도착, 들(도착 다음, 오두막을 연다), 마을(도착 다음, 탑과 왕녀 구출을 연다). 들과 마을이 갈림길이다."""
    return [
        chapter('arrival', '도착'),
        {**chapter('wild', '들', [reach(more['forest'])], places=[more['hut']]), 'after': ['arrival']},
        {
            **chapter('town', '마을', [reach(more['square'])], places=[more['tower']], quests=[more['rescue']]),
            'after': ['arrival'],
        },
    ]


def at(key: str) -> dict:
    return {'kind': 'chapter_at_least', 'chapter': key}


async def warnings_with(client: AsyncClient, me: dict, more: dict, **fields) -> list[str]:
    """갈림길의 판에 그 칸들(quests, happenings, achievements)을 적고 게시 점검의 알림을 본다."""
    scenario = await draft_with(client, me, more, forked(more))
    saved = await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json=fields, headers=me)
    assert saved.status_code == status.HTTP_200_OK, saved.text
    checked = await check(client, me, scenario)
    assert checked['problems'] == [], checked
    return checked['warnings']


def rescue(more: dict, conditions: list[dict], **fields) -> dict:
    return {'entry_id': more['rescue']['id'], 'start': 'active', 'conditions': conditions, **fields}


@pytest.mark.parametrize(
    ('case', 'expected'),
    [
        # 마을이 여는 퀘스트가 들이 여는 오두막을 기다린다
        ('opened-by-other-branch', ['quest_condition_locked']),
        # 마을이 여는 퀘스트가 마을이 여는 탑을 기다린다
        ('opened-on-the-route', []),
        # 마을이 여는 퀘스트가 그 앞의 도착을 기다린다(한 길이다)
        ('waits-for-an-earlier-chapter', []),
        # 실패하는 조건은 채워지지 않아도 된다
        ('fail-only', []),
        # 드러나는 조건이 다른 갈림길의 것을 기다린다
        ('reveal', ['quest_condition_locked']),
        # 하나라도: 조건 모두가 다른 갈림길의 것이면 알리고, 하나라도 마을 길에서 채울 수 있으면 알리지 않는다
        ('any-all-across', ['quest_condition_locked']),
        ('any-one-on-route', []),
    ],
)
async def test_a_quest_waiting_across_branches_is_warned(client: AsyncClient, me: dict, more: dict, case, expected):
    rules = {
        'opened-by-other-branch': rescue(more, [reach(more['hut'])]),
        'opened-on-the-route': rescue(more, [reach(more['tower'])]),
        'waits-for-an-earlier-chapter': rescue(more, [reach(more['tower']), at('arrival')]),
        'fail-only': rescue(more, [reach(more['tower'])], fail=[reach(more['hut'])]),
        'reveal': rescue(more, [reach(more['tower'])], start='hidden', reveal=[reach(more['hut'])]),
        'any-all-across': rescue(more, [reach(more['hut']), at('wild')], match='any'),
        'any-one-on-route': rescue(more, [reach(more['hut']), at('town')], match='any'),
    }

    assert await warnings_with(client, me, more, quests=[rules[case]]) == expected


@pytest.mark.parametrize(('match', 'expected'), [('all', ['happening_condition_locked']), ('any', [])])
async def test_a_happening_needing_both_branches_is_warned(client: AsyncClient, me: dict, more: dict, match, expected):
    storm = happening(more['storm'], [at('wild'), at('town')], [moving(more['gate'])], match=match)

    assert await warnings_with(client, me, more, happenings=[storm]) == expected


async def test_an_achievement_needing_both_branches_is_warned(client: AsyncClient, me: dict, more: dict):
    both = {'id': 'both', 'name': '둘 다', 'when': [reach(more['hut']), reach(more['tower'])]}
    one = {'id': 'one', 'name': '하나', 'when': [reach(more['hut']), at('wild')]}

    assert await warnings_with(client, me, more, achievements=[one]) == []
    assert await warnings_with(client, me, more, achievements=[one, both]) == ['achievement_condition_locked']


# --- 작은 함수 ---


def node(key: str, after: list[str] | None = None) -> ChapterLike:
    return cast(ChapterLike, SimpleNamespace(id=key, after=after or []))


def test_ancestors_follow_after_and_the_chapter_before():
    chapters = [node('a'), node('b'), node('c', ['a']), node('d', ['b', 'c'])]

    assert ancestors(chapters) == {'a': set(), 'b': {'a'}, 'c': {'a'}, 'd': {'a', 'b', 'c'}}
