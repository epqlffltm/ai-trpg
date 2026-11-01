# asset-server/tests/test_world_chapters.py

"""
세계관의 장(판의 형식 6, docs/architecture/chapters.md)을 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 장을 적어 게시하면 판(형식 6)에 그대로 굳는다. 고치기(PATCH)로 장만 바꿀 수 있다
  - 모양만으로 아는 것은 저장할 때 422 다. id 가 겹친다, 첫 장에 조건이 있다, 뒤의 장에 조건이 없다,
    장소나 이벤트 하나를 두 장에 적었다, chapter_at_least 에 대상이 없다
  - 게시를 막는 것: 없는 장소·이벤트를 연다(chapter_content_missing), 없는 장을 가리킨다(chapter_target_missing),
    시작 장소를 뒤의 장이 연다(chapter_start_locked)
  - 알리는 것: 넘어오는 조건이 그 장이나 뒤의 장에서야 열리는 것을 기다린다(chapter_unreachable)
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey

from app.worlds.documents import DOCUMENT_FORMAT
from tests.worlds import OWNER, WORLDS_URL, bearer, character, check, create_world, full_world, publish

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def owner(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OWNER)


def chapter(chapter_id: str, *items: dict, places: list[str] | None = None, events: list[str] | None = None) -> dict:
    """장 하나. 조건은 items 다."""
    return {
        'id': chapter_id,
        'name': f'{chapter_id} 장',
        'when': {'match': 'all', 'items': list(items)},
        'opens': {'places': places or [], 'events': events or []},
    }


SEEN_MEET = {'kind': 'event_seen', 'target': 'meet'}
# 1장(여름)에서 만남을 보면 2장(쪽지)이 열리고 옥상과 쪽지 이벤트가 열린다
CHAPTERS = [chapter('summer'), chapter('letters', SEEN_MEET, places=['roof'], events=['hint'])]


async def body_with(client: AsyncClient, headers: dict, **fields) -> dict:
    ari, beo = await character(client, headers, '아리'), await character(client, headers, '버')
    return {**full_world(ari['id'], beo['id']), **fields}


async def test_chapters_are_frozen_in_a_format_six_version(client: AsyncClient, owner: dict):
    world = await create_world(client, owner, await body_with(client, owner, chapters=CHAPTERS))

    checked = await check(client, owner, world)
    response = await publish(client, owner, world)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    document = response.json()['document']
    assert document['format'] == DOCUMENT_FORMAT == 6
    assert [entry['id'] for entry in document['chapters']] == ['summer', 'letters']
    assert document['chapters'][1]['opens'] == {'places': ['roof'], 'events': ['hint']}
    assert document['chapters'][1]['when']['items'] == [
        {'kind': 'event_seen', 'target': 'meet', 'value': None, 'count': 1}
    ]
    assert 'chapter_unreachable' not in checked['warnings']


async def test_chapters_can_be_patched_alone(client: AsyncClient, owner: dict):
    world = await create_world(client, owner, await body_with(client, owner))

    response = await client.patch(f'{WORLDS_URL}/{world["id"]}', json={'chapters': CHAPTERS}, headers=owner)

    assert response.status_code == status.HTTP_200_OK, response.text
    assert [entry['id'] for entry in response.json()['chapters']] == ['summer', 'letters']
    assert response.json()['events'] == world['events']


@pytest.mark.parametrize(
    'chapters',
    [
        [chapter('summer'), chapter('summer', SEEN_MEET)],
        [chapter('summer', SEEN_MEET)],
        [chapter('summer'), chapter('letters')],
        [chapter('summer', places=['roof']), chapter('letters', SEEN_MEET, places=['roof'])],
        [chapter('summer'), chapter('letters', {'kind': 'chapter_at_least'})],
    ],
    ids=['repeated-id', 'first-with-conditions', 'later-without-conditions', 'content-twice', 'no-target'],
)
async def test_shapes_known_without_the_rest_are_refused_on_save(client: AsyncClient, owner: dict, chapters: list):
    response = await client.post(WORLDS_URL, json=await body_with(client, owner, chapters=chapters), headers=owner)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    ('chapters', 'problem'),
    [
        ([chapter('summer'), chapter('letters', SEEN_MEET, places=['moon'])], 'chapter_content_missing'),
        ([chapter('summer'), chapter('letters', SEEN_MEET, events=['ghost'])], 'chapter_content_missing'),
        (
            [chapter('summer'), chapter('letters', {'kind': 'chapter_at_least', 'target': 'ghost'})],
            'chapter_target_missing',
        ),
        ([chapter('summer'), chapter('letters', SEEN_MEET, places=['school'])], 'chapter_start_locked'),
    ],
)
async def test_chapter_problems_block_publishing(client: AsyncClient, owner: dict, chapters: list, problem: str):
    world = await create_world(client, owner, await body_with(client, owner, chapters=chapters))

    checked = await check(client, owner, world)
    response = await publish(client, owner, world)

    assert checked['problems'] == [problem]
    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.parametrize(
    'items',
    [
        [{'kind': 'event_seen', 'target': 'hint'}],
        [{'kind': 'reach_place', 'target': 'roof'}],
        [{'kind': 'chapter_at_least', 'target': 'letters'}],
    ],
    ids=['event-of-its-own-chapter', 'place-of-its-own-chapter', 'its-own-chapter'],
)
async def test_a_chapter_waiting_for_its_own_content_is_warned(client: AsyncClient, owner: dict, items: list):
    chapters = [chapter('summer'), chapter('letters', *items, places=['roof'], events=['hint'])]
    world = await create_world(client, owner, await body_with(client, owner, chapters=chapters))

    checked = await check(client, owner, world)

    assert checked['problems'] == []
    assert 'chapter_unreachable' in checked['warnings']
