# trpg-server/tests/test_scenario_chapters.py

"""
시나리오의 장(#481 ①, docs/architecture/chapters.md)을 검증한다. 테이블이 장을 따르는 것은 다음 일이다.

맵과 픽스처는 tests/test_happenings.py 의 것이다. 성문(시작)-광장 큰길, 광장→지하실 숨긴 길, 성문-숲 안개 길,
오두막-숲 안개 길, 탑은 명소. 사건 항목 셋(함정, 휩쓸림, 왕녀 구출)과 맵 밖의 장소(지하 감옥), 물건(치유 물약)이 있다.

보는 것.
  - 저장: 장의 목록({id, name, when, match, opens})을 저장하고 고친다. 빠뜨린 칸은 기본값이다.
  - 모양(422): id 가 겹치거나, 첫 장에 조건이 있거나, 뒤의 장에 조건이 없거나, 장소나 퀘스트를 두 번 적거나,
    조건에 가져가기(consume)를 적거나, 장이 20 개를 넘으면 받지 않는다.
  - 게시(409): 맵에 없는 장소를 열거나, 로어북에 없거나 사건 항목이 아닌 것을 퀘스트로 열거나,
    조건이 틀렸거나(퀘스트의 조건과 같이 본다), 시작 장소를 첫 장 뒤에 열면 게시하지 않는다.
  - 판: 장이 판에 굳는다. 옛 판은 장이 없는 것으로 읽는다. 판도 틀린 장을 거부한다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError

from app.assets.scenarios.snapshot import Snapshot, read_snapshot
from tests import test_happenings as happening_tests
from tests.narration_model import asset_body
from tests.test_happenings import draft, publish, reach
from tests.test_table_items import SCENARIOS_URL

pytestmark = pytest.mark.usefixtures('clean_tables')

me = happening_tests.me
lore = happening_tests.lore
more = happening_tests.more


def chapter(key: str, name: str, when: list[dict] | None = None, **opens) -> dict:
    """장 하나. opens 는 places=, quests= 로 받은 항목들의 id 다."""
    opened = {kind: [entry['id'] for entry in entries] for kind, entries in opens.items()}
    return {'id': key, 'name': name, 'when': when or [], 'opens': opened}


def two_chapters(more: dict) -> list[dict]:
    """첫 장(도착)과, 광장에 닿으면 넘어가는 둘째 장(지하). 둘째 장이 지하실과 왕녀 구출을 연다."""
    return [
        chapter('arrival', '도착'),
        chapter('below', '지하', [reach(more['square'])], places=[more['cellar']], quests=[more['rescue']]),
    ]


async def draft_with(client: AsyncClient, me: dict, more: dict, chapters: list[dict]) -> dict:
    """그 장들을 적은 시나리오. 게시하지 않았다."""
    scenario = await draft(client, me, more, [])
    url = f'{SCENARIOS_URL}/{scenario["id"]}'
    response = await client.patch(url, json={'chapters': chapters}, headers=me)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


# --- 저장 ---


async def test_chapters_are_saved_with_their_defaults(client: AsyncClient, me: dict, more: dict):
    scenario = await draft_with(client, me, more, two_chapters(more))

    first, second = scenario['chapters']
    assert first == {
        'id': 'arrival',
        'name': '도착',
        'when': [],
        'match': 'all',
        'opens': {'places': [], 'quests': []},
        'after': [],
    }
    assert second['when'] == [{'kind': 'reach_place', 'target': more['square']['id'], 'count': 1, 'consume': False}]
    assert second['opens'] == {'places': [more['cellar']['id']], 'quests': [more['rescue']['id']]}


async def test_chapters_are_saved_when_the_scenario_is_made(client: AsyncClient, me: dict, more: dict):
    body = {'title': '성의 모험', 'chapters': [chapter('arrival', '도착')]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert [chapter['id'] for chapter in response.json()['chapters']] == ['arrival']


async def test_chapters_are_replaced_and_emptied(client: AsyncClient, me: dict, more: dict):
    scenario = await draft_with(client, me, more, two_chapters(more))
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    one = await client.patch(url, json={'chapters': [chapter('only', '하나뿐')]}, headers=me)
    none = await client.patch(url, json={'chapters': []}, headers=me)
    untouched = await client.patch(url, json={'title': '바꾼 제목'}, headers=me)

    assert [chapter['id'] for chapter in one.json()['chapters']] == ['only']
    assert none.json()['chapters'] == []
    assert untouched.json()['chapters'] == []


@pytest.mark.parametrize(
    'case',
    [
        'same-id',
        'first-with-when',
        'later-without-when',
        'place-twice',
        'quest-twice',
        'same-place-in-one',
        'consume',
        'too-many',
        'long-id',
        'blank-name',
    ],
)
async def test_a_misshaped_chapter_list_is_refused(client: AsyncClient, me: dict, more: dict, case: str):
    first = chapter('arrival', '도착')
    when = [reach(more['square'])]
    held = [{'kind': 'hold_item', 'target': more['potion']['id'], 'consume': True}]
    lists = {
        'same-id': [first, chapter('arrival', '다시', when)],
        'first-with-when': [chapter('arrival', '도착', when)],
        'later-without-when': [first, chapter('below', '지하')],
        'place-twice': [
            chapter('arrival', '도착', places=[more['cellar']]),
            chapter('b', '지하', when, places=[more['cellar']]),
        ],
        'quest-twice': [
            first,
            chapter('b', '지하', when, quests=[more['rescue']]),
            chapter('c', '끝', when, quests=[more['rescue']]),
        ],
        'same-place-in-one': [first, chapter('b', '지하', when, places=[more['cellar'], more['cellar']])],
        'consume': [first, chapter('b', '지하', held)],
        'too-many': [first, *[chapter(f'c{n}', f'{n}장', when) for n in range(20)]],
        'long-id': [chapter('x' * 41, '도착')],
        'blank-name': [chapter('arrival', '   ')],
    }
    body = {'title': '성의 모험', 'chapters': lists[case]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text


# --- 게시 ---


async def test_chapters_are_published_into_the_snapshot(client: AsyncClient, me: dict, more: dict):
    scenario = await draft_with(client, me, more, two_chapters(more))

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    first, second = read_snapshot(response.json()['snapshot']).chapters
    assert (first.id, first.name, first.when) == ('arrival', '도착', [])
    assert second.opens.places == [uuid.UUID(more['cellar']['id'])]
    assert second.opens.quests == [uuid.UUID(more['rescue']['id'])]
    assert second.when[0].target == uuid.UUID(more['square']['id'])


@pytest.mark.parametrize(
    ('case', 'problem'),
    [
        ('off-map', 'chapter_place_off_map'),
        ('quest-missing', 'chapter_quest_missing'),
        ('quest-not-event', 'chapter_quest_not_event'),
        ('condition-missing', 'chapter_condition_missing'),
        ('condition-invalid', 'chapter_condition_invalid'),
        ('condition-impossible', 'chapter_condition_impossible'),
        ('start-locked', 'chapter_start_locked'),
    ],
)
async def test_a_chapter_must_point_at_something_possible(
    client: AsyncClient, me: dict, more: dict, case: str, problem: str
):
    nowhere = {'id': str(uuid.uuid4())}
    first = chapter('arrival', '도착')
    when = [reach(more['square'])]
    lists = {
        'off-map': [first, chapter('b', '지하', when, places=[more['dungeon']])],
        'quest-missing': [first, chapter('b', '지하', when, quests=[nowhere])],
        'quest-not-event': [first, chapter('b', '지하', when, quests=[more['potion']])],
        'condition-missing': [first, chapter('b', '지하', [reach(nowhere)])],
        'condition-invalid': [first, chapter('b', '지하', [reach(more['potion'])])],
        # 맵에 없는 장소에는 아무도 설 수 없다
        'condition-impossible': [first, chapter('b', '지하', [reach(more['dungeon'])])],
        'start-locked': [first, chapter('b', '지하', when, places=[more['gate']])],
    }
    scenario = await draft_with(client, me, more, lists[case])

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == [problem]


async def test_the_start_place_may_be_opened_by_the_first_chapter(client: AsyncClient, me: dict, more: dict):
    chapters = [chapter('arrival', '도착', places=[more['gate']]), *two_chapters(more)[1:]]
    scenario = await draft_with(client, me, more, chapters)

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text


# --- 판 ---


async def test_the_snapshot_refuses_wrong_chapters(client: AsyncClient, me: dict, more: dict):
    scenario = await draft_with(client, me, more, two_chapters(more))
    document = (await publish(client, me, scenario)).json()['snapshot']
    first, second = document['chapters']
    wrong = {
        'off-place': [first, {**second, 'opens': {'places': [str(uuid.uuid4())], 'quests': []}}],
        'not-event': [first, {**second, 'opens': {'places': [], 'quests': [more['potion']['id']]}}],
        'first-when': [{**first, 'when': second['when']}, second],
        'start-locked': [first, {**second, 'opens': {'places': [more['gate']['id']], 'quests': []}}],
    }

    for chapters in wrong.values():
        with pytest.raises(ValidationError):
            Snapshot.model_validate({**document, 'chapters': chapters})
    Snapshot.model_validate(document)


async def test_an_old_snapshot_reads_as_no_chapters(client: AsyncClient, me: dict, more: dict):
    document = (await publish(client, me, await draft(client, me, more, []))).json()['snapshot']
    del document['chapters']

    assert Snapshot.model_validate(document).chapters == []
