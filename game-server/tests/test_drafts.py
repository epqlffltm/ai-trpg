# game-server/tests/test_drafts.py

"""
장부 초안: 장면에서 물건을 손에 넣은 일과 퀘스트의 변화를 구조화한 데이터로 뽑는다.

다섯을 본다.
  - 답 읽기: JSON 이고 모양이 맞아야 한다. 틀리면 통째로 버린다(고쳐 읽지 않는다).
  - 목록: 살아 있는 캐릭터, 판의 물건, 끝나지 않은 퀘스트에 이름표를 붙인다.
  - 검증: 목록에 없는 것, 바꿀 수 없는 퀘스트, 겹친 초안을 까닭과 함께 버린다.
  - 메시지: 목록과 장면이 들어간다.
  - 부르기: 초안에 적을 거리가 없으면 부르지 않는다. 실패해도 예외 없이 빈 결과다. 어떻게 끝났든 기록을 남긴다.
"""

import uuid
from dataclasses import dataclass
from typing import ClassVar

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.calls import Outcome, chars_of
from app.ai.fake import FakeCallLog, FakeProvider
from app.ai.provider import ChatMessage, Completion, GenerationParams, ProviderError, Role
from app.assets.scenarios.snapshot import read_snapshot
from app.drafts.context import (
    CharacterChoice,
    DraftContext,
    ItemChoice,
    QuestChoice,
    build_context,
    has_choices,
)
from app.drafts.output import DraftOutput, OutputError, read_output
from app.drafts.prompt import DRAFT_PROMPT_VERSION, SYSTEM_TEXT, build_messages
from app.drafts.validation import NOTHING, ItemDraft, QuestDraft, Rejected, check_output
from app.drafts.writer import DRAFT_PARAMS, DraftRequest, DraftWriter
from app.tables import repository as table_repository
from app.tables.models import QuestStatus
from tests import test_table_quests as quest_tables
from tests.test_table_items import FRIEND, ME, kill
from tests.test_table_quests import change, start_duo

pytestmark = pytest.mark.usefixtures('clean_tables')

# 퀘스트 테스트의 픽스처를 그대로 쓴다. 방장(기사), 함께 앉는 사람(약사), 사건과 물건이 든 로어북
me = quest_tables.me
friend = quest_tables.friend
lore = quest_tables.lore

KNIGHT = uuid.UUID('11111111-2222-4333-8444-555555555555')
POTION = uuid.UUID('cccccccc-0000-4000-8000-000000000001')
RESCUE = uuid.UUID('cccccccc-0000-4000-8000-000000000002')
MINE = uuid.UUID('cccccccc-0000-4000-8000-000000000003')

SCENE = '기사는 상자에서 치유 물약 둘을 꺼냈다. 왕녀가 감옥에서 풀려났다.'

# 기사 하나, 물약 하나, 퀘스트 둘(진행 중인 왕녀 구출, 광산의 비밀). 숨긴 퀘스트는 목록에 없다(ledger-draft-6)
CONTEXT = DraftContext(
    characters={'p1': CharacterChoice('p1', KNIGHT, '기사')},
    items={'i1': ItemChoice('i1', POTION, '치유 물약')},
    quests={
        'q1': QuestChoice('q1', RESCUE, '왕녀 구출', QuestStatus.ACTIVE),
        'q2': QuestChoice('q2', MINE, '광산의 비밀', QuestStatus.ACTIVE),
    },
)

GOOD_REPLY = (
    '{"found_items": [{"character": "p1", "item": "i1", "count": 2}], '
    '"quest_changes": [{"quest": "q1", "status": "failed"}]}'
)


# --- 답 읽기 ---


def test_a_reply_is_read_as_drafts():
    output = read_output(GOOD_REPLY)

    assert [(item.character, item.item, item.count) for item in output.found_items] == [('p1', 'i1', 2)]
    assert [(quest.quest, quest.status) for quest in output.quest_changes] == [('q1', 'failed')]


def test_a_fenced_reply_is_unwrapped():
    assert read_output(f'```json\n{GOOD_REPLY}\n```') == read_output(GOOD_REPLY)


def test_nothing_happened_is_a_fine_reply():
    assert read_output('{}') == DraftOutput()


@pytest.mark.parametrize('text', ['물약을 찾았습니다.', '', '{"found_items": ['])
def test_a_reply_that_is_not_json_is_refused(text: str):
    with pytest.raises(OutputError) as raised:
        read_output(text)

    assert raised.value.reason == 'not_json'


@pytest.mark.parametrize(
    'text',
    [
        '[]',
        '{"found_items": [{"character": "p1", "item": "i1", "count": 0}]}',
        '{"found_items": [{"character": "p1", "item": "i1", "count": 100}]}',
        '{"found_items": [{"character": "기사", "item": "i1", "count": 1}]}',
        '{"found_items": [{"character": "p1", "item": "i1"}]}',
        '{"found_items": [{"character": "p1", "item": "i1", "count": 1, "why": "상자"}]}',
        '{"quest_changes": [{"quest": "q1", "status": "hidden"}]}',
        '{"quest_changes": [{"quest": "q1", "status": "done"}]}',
        '{"notes": "없음"}',
        '{"found_items": [' + ', '.join(['{"character": "p1", "item": "i1", "count": 1}'] * 9) + ']}',
    ],
    ids=[
        'not-an-object',
        'zero',
        'too-many',
        'name-not-label',
        'no-count',
        'extra-field',
        'hide-again',
        'made-up-status',
        'unknown-key',
        'too-long-a-list',
    ],
)
def test_a_badly_shaped_reply_is_refused_as_a_whole(text: str):
    with pytest.raises(OutputError) as raised:
        read_output(text)

    assert raised.value.reason == 'bad_shape'


# --- 검증 ---


def test_drafts_within_the_lists_are_accepted():
    checked = check_output(read_output(GOOD_REPLY), CONTEXT)

    assert checked.items == [ItemDraft(KNIGHT, '기사', POTION, '치유 물약', 2)]
    assert checked.quests == [QuestDraft(RESCUE, '왕녀 구출', QuestStatus.ACTIVE, QuestStatus.FAILED)]
    assert checked.rejected == []


@pytest.mark.parametrize(
    ('document', 'rejected'),
    [
        ({'found_items': [{'character': 'p2', 'item': 'i1', 'count': 1}]}, Rejected('found_item', 'unknown_character')),
        ({'found_items': [{'character': 'p1', 'item': 'i9', 'count': 1}]}, Rejected('found_item', 'unknown_item')),
        ({'quest_changes': [{'quest': 'q7', 'status': 'failed'}]}, Rejected('quest_change', 'unknown_quest')),
        # 드러내기도 엔진이 조건을 보고 정한다(ledger-draft-6, #367)
        ({'quest_changes': [{'quest': 'q1', 'status': 'active'}]}, Rejected('quest_change', 'quest_reveal_by_engine')),
        (
            {'quest_changes': [{'quest': 'q1', 'status': 'succeeded'}]},
            Rejected('quest_change', 'quest_success_by_engine'),
        ),
    ],
    ids=['made-up-character', 'made-up-item', 'made-up-quest', 'reveal-is-for-the-engine', 'success-is-for-the-engine'],
)
def test_drafts_outside_the_rules_are_rejected_with_a_reason(document: dict, rejected: Rejected):
    checked = check_output(DraftOutput.model_validate(document), CONTEXT)

    assert (checked.items, checked.quests, checked.rejected) == ([], [], [rejected])


def test_the_same_draft_twice_keeps_the_first():
    document = {
        'found_items': [
            {'character': 'p1', 'item': 'i1', 'count': 2},
            {'character': 'p1', 'item': 'i1', 'count': 5},
        ],
        'quest_changes': [{'quest': 'q2', 'status': 'failed'}, {'quest': 'q2', 'status': 'failed'}],
    }

    checked = check_output(DraftOutput.model_validate(document), CONTEXT)

    assert [item.count for item in checked.items] == [2]
    assert [quest.entry_id for quest in checked.quests] == [MINE]
    assert checked.rejected == [Rejected('found_item', 'duplicate'), Rejected('quest_change', 'duplicate')]


def test_a_bad_draft_does_not_spoil_the_good_ones():
    document = {
        'found_items': [
            {'character': 'p9', 'item': 'i1', 'count': 1},
            {'character': 'p1', 'item': 'i1', 'count': 1},
        ]
    }

    checked = check_output(DraftOutput.model_validate(document), CONTEXT)

    assert [item.character_name for item in checked.items] == ['기사']
    assert checked.rejected == [Rejected('found_item', 'unknown_character')]


# --- 목록 ---


async def context_of(session: AsyncSession, table: dict) -> DraftContext:
    """테이블을 DB 에서 읽어 목록을 만든다."""
    found = await table_repository.find_table(session, uuid.UUID(table['id']))
    return build_context(found, read_snapshot(found.content))


def described(context: DraftContext) -> tuple[list, list, list]:
    """목록을 (이름표, 이름[, 상태])로."""
    return (
        [(choice.label, choice.name) for choice in context.characters.values()],
        [(choice.label, choice.name) for choice in context.items.values()],
        [(choice.label, choice.name, choice.status) for choice in context.quests.values()],
    )


async def test_the_lists_come_from_the_table(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)

    characters, things, quests = described(await context_of(session, table))

    assert characters == [('p1', '기사'), ('p2', '약사')]
    assert things == [('i1', '치유 물약'), ('i2', '밧줄')]
    # 숨긴 광산의 비밀과 배신자는 없다. 초안은 방장이 보므로 숨긴 퀘스트의 이름이 새면 안 된다
    assert quests == [('q1', '왕녀 구출', QuestStatus.ACTIVE)]


async def test_the_dead_and_the_finished_are_left_out(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    await change(client, me, table, lore['rescue'], 'failed')
    await kill(session, FRIEND)

    context = await context_of(session, table)
    characters, _, quests = described(context)

    # 이름표는 남은 것끼리 다시 붙는다
    assert characters == [('p1', '기사')]
    assert context.characters['p1'].user_id == ME
    # 끝난 왕녀 구출도 빠졌다. 남은 것은 숨긴 것뿐이라 퀘스트 목록이 비었다
    assert quests == []


@pytest.mark.parametrize(
    ('characters', 'things', 'quests', 'expected'),
    [
        (True, True, False, True),
        (False, False, True, True),
        (True, False, False, False),
        (False, True, False, False),
        (False, False, False, False),
    ],
    ids=['someone-and-something', 'a-quest', 'nothing-to-find', 'nobody-to-receive', 'empty'],
)
def test_there_is_something_to_draft(characters: bool, things: bool, quests: bool, expected: bool):
    context = DraftContext(
        characters=CONTEXT.characters if characters else {},
        items=CONTEXT.items if things else {},
        quests=CONTEXT.quests if quests else {},
    )

    assert has_choices(context) is expected


# --- 메시지 ---


def test_the_rules_keep_items_passed_between_characters_out():
    # ledger-draft-2: 캐릭터끼리 건넨 것을 손에 넣은 일로 적으면 장부에 물건이 하나 더 생긴다(#229)
    assert '캐릭터끼리 물건을 건넨 것은 넣지 않는다' in SYSTEM_TEXT
    assert '마지막에 가진 캐릭터 하나만 넣는다' in SYSTEM_TEXT


def test_the_place_for_unlisted_items_is_gone_again():
    # ledger-draft-4: -3 의 자리(unlisted_items)는 드러난 퀘스트를 놓치게 해서 뺐다. 그 칸이 오면 모양이 틀린 답이다
    # ledger-draft-5: 이룬 일(succeeded)은 엔진이 정한다
    # ledger-draft-6: 드러난 일(active)도 엔진이 정한다
    assert DRAFT_PROMPT_VERSION == 'ledger-draft-6'
    assert 'unlisted_items' not in SYSTEM_TEXT
    with pytest.raises(OutputError) as raised:
        read_output('{"found_items": [], "unlisted_items": ["녹슨 장검"]}')
    assert raised.value.reason == 'bad_shape'


def test_the_message_lists_the_choices_and_the_scene():
    [system, user] = build_messages(SCENE, CONTEXT)

    assert (system.role, system.content) == (Role.SYSTEM, SYSTEM_TEXT)
    assert user.role == Role.USER
    assert user.content == '\n'.join(
        [
            '[캐릭터]',
            '- p1: 기사',
            '[물건]',
            '- i1: 치유 물약',
            '[퀘스트]',
            '- q1: 왕녀 구출 (진행 중)',
            '- q2: 광산의 비밀 (진행 중)',
            '',
            '[장면]',
            SCENE,
        ]
    )


def test_an_empty_list_says_so():
    context = DraftContext(characters={}, items={}, quests=CONTEXT.quests)

    [_, user] = build_messages(SCENE, context)

    assert '[캐릭터]\n(없음)\n[물건]\n(없음)\n[퀘스트]' in user.content


# --- 부르기 ---


@dataclass
class BrokenProvider:
    """부를 때마다 실패하는 provider. 이유는 짧은 낱말이다(본문을 싣지 않는다)."""

    kind: ClassVar[str] = 'broken'
    model: str = 'broken'

    async def complete(self, messages: list[ChatMessage], params: GenerationParams, on_text=None) -> Completion:
        raise ProviderError('timeout')


def request() -> DraftRequest:
    return DraftRequest(scene=SCENE, context=CONTEXT, table_id=uuid.uuid4(), round_number=3, host_id=KNIGHT)


async def test_the_writer_returns_what_survived_and_logs_the_call():
    provider, log = FakeProvider(reply=GOOD_REPLY), FakeCallLog()
    sent = request()

    checked = await DraftWriter(provider, log).draft(sent)

    assert [item.count for item in checked.items] == [2]
    assert [quest.status for quest in checked.quests] == [QuestStatus.FAILED]
    [call] = provider.calls
    assert (call.messages, call.params) == (build_messages(SCENE, CONTEXT), DRAFT_PARAMS)
    [record] = log.records
    assert (record.scope.purpose, record.scope.table_id, record.scope.round_number) == (
        'ledger_draft',
        sent.table_id,
        3,
    )
    assert (record.outcome, record.prompt_version, record.temperature, record.text) == (
        Outcome.OK,
        DRAFT_PROMPT_VERSION,
        0.0,
        GOOD_REPLY,
    )
    # 입력 토큰 수와 견주어 글자당 토큰 수를 잰다(app/rounds/budget.py)
    assert record.input_chars == chars_of(call.messages)


async def test_nothing_to_draft_calls_nobody():
    provider, log = FakeProvider(reply=GOOD_REPLY), FakeCallLog()
    empty = DraftRequest(scene=SCENE, context=DraftContext(characters={}, items={}, quests={}))

    assert await DraftWriter(provider, log).draft(empty) is NOTHING
    assert (provider.calls, log.records) == ([], [])


@pytest.mark.parametrize(
    ('provider', 'outcome', 'error'),
    [
        (BrokenProvider(), Outcome.FAILED, 'timeout'),
        (FakeProvider(reply=GOOD_REPLY, truncated=True), Outcome.REJECTED, 'cut_off'),
        (FakeProvider(reply='물약을 찾았습니다.'), Outcome.REJECTED, 'not_json'),
        (FakeProvider(reply='{"items": []}'), Outcome.REJECTED, 'bad_shape'),
    ],
    ids=['provider-failed', 'cut-off', 'not-json', 'bad-shape'],
)
async def test_a_failed_draft_is_nothing_but_still_logged(provider, outcome: Outcome, error: str):
    log = FakeCallLog()

    # 초안은 덤이다. 예외를 올리지 않는다. 방장은 손으로 하던 대로 하면 된다
    assert await DraftWriter(provider, log).draft(request()) is NOTHING
    [record] = log.records
    assert (record.outcome, record.error) == (outcome, error)
