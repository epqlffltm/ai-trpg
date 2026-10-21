# trpg-server/tests/test_references_narration.py

"""
참고 자료를 서술에 섞는 것(#482 2단계)을 검증한다.

보는 것.
  - 켤 수 있는가(app/references/policy.py): 세계관이 없거나, 세계관이 허용했을 때만.
    옛 판은 허용하지 않은 것으로 읽는다.
  - 세계관의 칸(references_allowed), 공개 소개(references_allowed), 테이블의 칸(references_enabled)과 바꾸는 길.
    방장만, 모집 중에만 바꾼다. 허용하지 않는 판에서 켜면 422 다. 바꾼 것은 이벤트로 남는다.
  - 고르기(app/references/retrieval.py): 로어북이 쓰고 남은 자리에만, 다른 이름으로 걸린 것을 먼저, 거리 기준 안에서.
    테이블이 켜지 않았으면 고르지 않는다. 임베딩 모델이 실패하면 다른 이름으로만 고른다.
  - 프롬프트: [참고할 설정] 뒤의 [참고 자료]. 없으면 붙지 않는다. 예산을 넘으면 참고 자료를 가장 먼저 뺀다.
  - 호출 기록에 넣은 줄(reference_ids)이 남는다. 테이블을 끝까지 돌리면 서술자가 참고 자료를 받는다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.fake import FakeCallLog, FakeEmbedder, FakeProvider
from app.assets.scenarios.upgrades import upgrade_from_41
from app.lore.retrieval import LORE_MAX_CHARS
from app.references.indexing import index_references
from app.references.loading import load_document
from app.references.policy import references_allowed
from app.references.records import (
    ReferenceDocument,
    ReferenceKind,
    ReferenceOrigin,
    ReferenceRecord,
    ReferenceSource,
    StoredReference,
)
from app.references.retrieval import (
    ReferenceRetriever,
    ReferenceThresholds,
    alias_hits,
    choose,
    room_for,
)
from app.rounds import budget, prompt
from app.rounds.llm_narrator import LLMNarrator
from app.rounds.narrator import LoreNote, Move, NarrationRequest, ReferenceNote, StoryContext
from tests import test_npc_actions as npc_tests
from tests.previews import RecordingPreview
from tests.sheets import SHEET
from tests.test_npc_actions import (
    OPENING,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    TABLES_URL,
    RecordingNarrator,
    declare,
    events_of,
    post,
    table_url,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

me = npc_tests.me
friend = npc_tests.friend

WORLDS_URL = f'{TABLES_URL.removesuffix("/tables")}/worlds'
STORY = StoryContext(title='추격전', rating='all', guide='추격은 바이크로 한다.')
TORCH = ReferenceRecord(
    key='equipment/torch',
    kind=ReferenceKind.ITEM,
    name='Torch',
    aliases=['횃불'],
    content='A torch burns for 1 hour, providing bright light.',
)
SHIP = ReferenceRecord(key='equipment/sailing-ship', kind=ReferenceKind.ITEM, name='Sailing ship', content='Ship.')
# 테스트의 가짜 임베더는 낱말이 겹치는지만 본다. 거리 기준을 넓혀 고르는 길만 본다
WIDE = ReferenceThresholds(max_distance=2, keyword_max_distance=2)
LIGHT = '횃불을 들어 동굴을 비춘다.'


def stored(name: str, aliases: list[str] | None = None, content: str = '') -> StoredReference:
    return StoredReference(id=uuid.uuid4(), key=name, name=name, aliases=aliases or [], content=content)


def request(lore: list[LoreNote] | None = None, table_id: uuid.UUID | None = None) -> NarrationRequest:
    return NarrationRequest(
        round_number=1,
        scene=OPENING,
        moves=[Move('엘프', LIGHT)],
        story=STORY,
        table_id=table_id,
        lore=lore or [],
    )


def document(*records: ReferenceRecord) -> ReferenceDocument:
    origin = ReferenceOrigin(dataset='test', revision='abc', license='CC-BY-4.0', attribution='SRD 5.1')
    return ReferenceDocument(format=1, source=ReferenceSource.SRD51, origin=origin, entries=list(records))


async def put_references(client: AsyncClient, headers: dict, table: dict, enabled: bool):
    return await client.put(table_url(table, '/references'), json={'references_enabled': enabled}, headers=headers)


async def open_table(client: AsyncClient, me: dict, allowed: bool | None, enabled: bool = False, capacity: int = 1):
    """
    시나리오를 만들어 테이블을 연다(모집 중). allowed 가 None 이면 세계관이 없다. 시나리오와 테이블의 응답이다.

    enabled 로 만들 때 참고 자료를 켠다. 만들기가 거절되면 테이블 자리에 응답이 온다.
    """
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    body = {'title': '동굴', 'rulebook_id': rulebook['id'], 'openings': [OPENING], 'default_sheet': SHEET}
    if allowed is not None:
        world = await post(client, WORLDS_URL, me, title='세계관', references_allowed=allowed)
        body['world_id'] = world['id']
    scenario = await post(client, SCENARIOS_URL, me, **body)
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = {'scenario_id': scenario['id'], 'version': 1, 'capacity': capacity, 'references_enabled': enabled}
    response = await client.post(TABLES_URL, json=table, headers=me)
    return scenario, response


async def start_alone(client: AsyncClient, me: dict, table: dict) -> None:
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text


# --- 켤 수 있는가 ---


@pytest.mark.parametrize(('world', 'allowed'), [(None, True), (False, False), (True, True)])
def test_only_a_world_that_allows_it_or_no_world_can_turn_it_on(world: bool | None, allowed: bool):
    snapshot = SimpleNamespace(world=None if world is None else SimpleNamespace(references_allowed=world))

    assert references_allowed(snapshot) is allowed


def test_an_old_version_reads_its_world_as_not_allowing():
    old = {'format': 41, 'world': {'id': 'w', 'title': '세계', 'setting': '', 'gm_notes': ''}}

    assert upgrade_from_41(old)['world']['references_allowed'] is False
    assert upgrade_from_41({'format': 41, 'world': None}) == {'format': 42, 'world': None}


async def test_the_world_carries_the_permission(client: AsyncClient, me: dict):
    world = await post(client, WORLDS_URL, me, title='세계관')
    changed = await client.patch(f'{WORLDS_URL}/{world["id"]}', json={'references_allowed': True}, headers=me)

    assert world['references_allowed'] is False
    assert changed.json()['references_allowed'] is True


async def test_the_public_listing_says_whether_it_can_be_turned_on(client: AsyncClient, me: dict, friend: dict):
    scenario, _ = await open_table(client, me, allowed=False)
    listing_url = f'{SCENARIOS_URL}/{scenario["id"]}/listing'
    await client.patch(listing_url, json={'tagline': '어둡다', 'genres': ['fantasy']}, headers=me)
    published = await client.put(f'{listing_url}/publication', json={'version': 1}, headers=me)
    assert published.status_code == status.HTTP_200_OK, published.text

    detail = await client.get(f'{TABLES_URL.removesuffix("/tables")}/listings/{scenario["id"]}', headers=friend)

    assert detail.status_code == status.HTTP_200_OK, detail.text
    assert detail.json()['references_allowed'] is False


# --- 테이블의 칸 ---


async def test_a_table_can_be_made_with_references_where_allowed(client: AsyncClient, me: dict):
    _, allowed = await open_table(client, me, allowed=True, enabled=True)
    _, without_world = await open_table(client, me, allowed=None, enabled=True)
    _, refused = await open_table(client, me, allowed=False, enabled=True)

    assert allowed.status_code == status.HTTP_201_CREATED and allowed.json()['references_enabled'] is True
    assert without_world.json()['references_enabled'] is True
    assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'references_enabled' in refused.json()['detail']


async def test_the_host_turns_it_on_while_recruiting_and_everyone_sees_it(client: AsyncClient, me: dict, friend: dict):
    _, response = await open_table(client, me, allowed=True, capacity=2)
    table = response.json()
    await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)

    by_friend = await put_references(client, friend, table, True)
    turned = await put_references(client, me, table, True)
    again = await put_references(client, me, table, True)

    assert by_friend.status_code == status.HTTP_403_FORBIDDEN
    assert turned.status_code == status.HTTP_200_OK and turned.json()['references_enabled'] is True
    assert again.status_code == status.HTTP_200_OK
    # 같은 값이면 이벤트가 쌓이지 않는다
    (event,) = await events_of(client, friend, table, 'references_changed')
    assert event['payload'] == {'references_enabled': True}


async def test_it_is_fixed_once_the_table_starts(client: AsyncClient, me: dict):
    _, response = await open_table(client, me, allowed=True)
    table = response.json()
    await start_alone(client, me, table)

    locked = await put_references(client, me, table, True)

    assert locked.status_code == status.HTTP_409_CONFLICT
    assert locked.json()['reason'] == 'not_recruiting'


async def test_it_cannot_be_turned_on_where_the_world_does_not_allow_it(client: AsyncClient, me: dict):
    _, response = await open_table(client, me, allowed=False)
    table = response.json()

    refused = await put_references(client, me, table, True)
    off = await put_references(client, me, table, False)

    assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert off.status_code == status.HTTP_200_OK


# --- 고르기 ---


def test_the_room_is_what_the_lore_left():
    small = LoreNote(entry_id=uuid.uuid4(), name='동굴', content='가' * 98)
    full = LoreNote(entry_id=uuid.uuid4(), name='동굴', content='가' * (LORE_MAX_CHARS - 2))

    assert room_for(request()) == 1500
    assert room_for(request([small]), max_chars=5000) == LORE_MAX_CHARS - 100
    assert room_for(request([full])) == 0


def test_aliases_are_matched_but_original_names_are_not():
    torch = stored('Torch', ['횃불'])
    bat = stored('Bat')

    assert alias_hits([torch, bat], '횃불을 들고 Battle 을 외친다') == [torch]


def test_choosing_puts_near_alias_hits_first_within_room_and_limit():
    near_hit, far_hit, unknown_hit = stored('A', ['가'], 'x' * 10), stored('B', ['나']), stored('C', ['다'], 'y')
    nearest = [stored('D', content='z' * 10), stored('E', content='w' * 400), near_hit]
    distances = {near_hit.id: 0.2, far_hit.id: 0.9}
    thresholds = ReferenceThresholds(limit=3)

    picked = choose([near_hit, far_hit, unknown_hit], distances, nearest, thresholds, room=100)

    # 먼 다른 이름은 빠지고, 거리를 모르는 것은 들어간다. 넘치는 줄은 건너뛰고 같은 줄은 한 번만
    assert [reference.name for reference in picked] == ['A', 'C', 'D']


async def test_the_retriever_finds_only_for_tables_that_turned_it_on(
    app: FastAPI, client: AsyncClient, session: AsyncSession, me: dict
):
    await load_document(session, document(TORCH, SHIP))
    await index_references(app.state.session_factory, app.state.embedder)
    _, on = await open_table(client, me, allowed=True, enabled=True)
    _, off = await open_table(client, me, allowed=True)
    retriever = ReferenceRetriever(app.state.session_factory, app.state.embedder, WIDE)

    found = await retriever.find(request(table_id=uuid.UUID(on.json()['id'])))
    nothing = await retriever.find(request(table_id=uuid.UUID(off.json()['id'])))

    assert [note.name for note in found][:1] == ['Torch']
    assert found[0].kind == 'item' and '횃불' not in found[0].content
    assert nothing == []


async def test_without_the_embedder_only_aliases_are_found(
    app: FastAPI, client: AsyncClient, session: AsyncSession, me: dict
):
    await load_document(session, document(TORCH, SHIP))
    _, on = await open_table(client, me, allowed=True, enabled=True)
    retriever = ReferenceRetriever(app.state.session_factory, FakeEmbedder(error='timeout'), WIDE)

    found = await retriever.find(request(table_id=uuid.UUID(on.json()['id'])))

    assert [note.name for note in found] == ['Torch']


# --- 프롬프트와 기록 ---

NOTE = ReferenceNote(reference_id=uuid.uuid4(), name='Torch', content='A torch burns.', kind='item')


def test_the_references_come_after_the_settings_in_the_prompt():
    lore = [LoreNote(entry_id=uuid.uuid4(), name='동굴', content='어둡다')]
    with_notes = prompt.round_text(NarrationRequest(**{**request(lore).__dict__, 'references': [NOTE]}))
    without = prompt.round_text(request(lore))

    assert with_notes.index(prompt.LORE_TITLE) < with_notes.index(prompt.REFERENCE_TITLE)
    assert '- [물건] Torch: A torch burns.' in with_notes
    assert prompt.REFERENCE_TITLE not in without


def test_the_references_are_dropped_first_when_the_input_is_too_long():
    lore = [LoreNote(entry_id=uuid.uuid4(), name='동굴', content='어둡다')]
    full = NarrationRequest(**{**request(lore).__dict__, 'references': [NOTE, NOTE]})

    steps = list(budget.trimmed(full))

    assert [len(step.references) for step in steps[:3]] == [2, 1, 0]
    assert all(step.lore == lore for step in steps[:3])


async def test_the_call_records_the_references_it_sent():
    log = FakeCallLog()
    sent = NarrationRequest(**{**request().__dict__, 'references': [NOTE]})

    await LLMNarrator(FakeProvider(reply='횃불이 타오른다.'), log).narrate(sent, RecordingPreview())

    (record,) = log.records
    assert record.reference_ids == (NOTE.reference_id,)


async def test_a_table_with_references_hands_them_to_the_narrator(
    app: FastAPI, client: AsyncClient, session: AsyncSession, me: dict, narrated
):
    await load_document(session, document(TORCH))
    await index_references(app.state.session_factory, app.state.embedder)
    app.state.references = ReferenceRetriever(app.state.session_factory, app.state.embedder, WIDE)
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    _, response = await open_table(client, me, allowed=True, enabled=True)
    table = response.json()
    await start_alone(client, me, table)

    await declare(client, me, table, LIGHT)
    await narrated()

    (sent,) = narrator.requests
    assert [note.name for note in sent.references] == ['Torch']
