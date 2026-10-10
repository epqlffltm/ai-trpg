# game-server/tests/test_person_history.py

"""
장면에 나온 인물의 이력(app/memory/history.py)을 검증한다. 모델을 부르지 않는다.

보는 것은 셋이다.
  - 문장으로 나누고, 모을 서술을 고르고, 인물이 나온 문장을 최근 것부터 고르는 순수한 함수들.
  - 로어북이 고른 인물 항목마다 테이블의 지난 서술에서 이력을 모은다. 인물이 아닌 항목, 이력이 빈 인물은 뺀다.
  - 라운드를 닫으면 이력이 프롬프트에 "인물의 이력"으로 들어간다.
"""

import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.ai.call_log import DbCallLog
from app.ai.fake import FakeProvider
from app.assets.models import LoreKind
from app.assets.scenarios.snapshot import EntrySnapshot
from app.lore.retrieval import load_candidates
from app.memory.history import (
    HISTORY_LINES,
    HISTORY_PEOPLE,
    HistoryCollector,
    history_of,
    latest,
    lines_about,
    scene_lines,
    sentences,
)
from app.rounds import prompt
from app.rounds.llm_narrator import LLMNarrator
from app.rounds.narrator import (
    HistoryLine,
    LoreNote,
    MemoryNote,
    Move,
    NarrationRequest,
    PastRound,
    PersonHistory,
    StoryContext,
)
from tests.signing import SigningKey, make_access_claims, make_token

# 테이블을 열고 라운드를 진행하는 도우미와 예시는 지난 일의 테스트와 같은 것을 쓴다
from tests.test_memory import CURRENT, LADY, ME, open_table, play, played_table

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(ME)))
    return {'Authorization': f'Bearer {token}'}


def person(name: str, *keywords: str) -> EntrySnapshot:
    return EntrySnapshot(id=uuid.uuid4(), name=name, keywords=list(keywords), content='', kind=LoreKind.PERSON)


def line(number: int, text: str) -> HistoryLine:
    return HistoryLine(round_number=number, text=text)


# --- 문장 ---


def test_a_scene_is_split_into_sentences():
    text = '악역영애가 웃었다. 정말? 그래! 바람이 분다…\n엔진이 울었다'

    assert sentences(text) == ['악역영애가 웃었다.', '정말?', '그래!', '바람이 분다…', '엔진이 울었다']


def test_a_closing_quote_stays_with_its_sentence():
    assert sentences('"어머, 무례하기도 해라." 악역영애가 웃었다.') == [
        '"어머, 무례하기도 해라."',
        '악역영애가 웃었다.',
    ]


def test_a_line_without_an_ending_mark_is_a_sentence():
    # 서술이 마침표 없이 줄을 바꾸기도 한다
    assert sentences('엔진이 울었다\n악역영애가 웃었다.') == ['엔진이 울었다', '악역영애가 웃었다.']


def test_blank_pieces_are_dropped():
    assert sentences('  \n\n악역영애가 웃었다.  \n ') == ['악역영애가 웃었다.']


def test_only_scenes_before_the_recent_rounds_and_after_the_opening_are_used():
    rounds = [PastRound(number=number, scene=f'{number} 라운드의 장면.') for number in range(1, 10)]

    # 9 라운드를 서술할 때 지난 기록은 6, 7, 8 라운드다. 1 라운드의 장면은 도입부다
    assert [item.round_number for item in scene_lines(rounds, 9)] == [2, 3, 4, 5]


def test_scene_lines_follow_the_story_order():
    rounds = [PastRound(number=3, scene='셋째. 넷째.'), PastRound(number=2, scene='첫째. 둘째.')]

    assert scene_lines(rounds, 9) == [line(2, '첫째.'), line(2, '둘째.'), line(3, '셋째.'), line(3, '넷째.')]


def test_lines_about_a_person_are_those_with_the_name_or_a_keyword():
    lady = person('비올레타', '악역영애', '부채')
    lines = [line(2, '악역영애가 웃었다.'), line(3, '비가 왔다.'), line(4, '부채가 접혔다.'), line(5, '비올레타 님!')]

    assert lines_about(lady, lines) == [lines[0], lines[2], lines[3]]


def test_latest_lines_are_kept_in_the_story_order():
    lines = [line(number, f'{number} 라운드.') for number in range(2, 9)]

    # 최근 일이 지금의 태도에 가깝다. 고른 뒤에는 이야기의 순서로 놓는다
    assert latest(lines, 3, 1000) == lines[-3:]


def test_a_line_too_long_is_skipped_for_an_older_one():
    lines = [line(2, '짧다.'), line(3, '가' * 50), line(4, '짧다.')]

    assert latest(lines, 5, 20) == [lines[0], lines[2]]


def test_a_history_is_the_latest_lines_about_the_person():
    lady = person('비올레타', '악역영애')
    lines = [line(number, f'{number} 라운드에 악역영애가 웃었다.') for number in range(2, 12)]

    history = history_of(lady, [*lines, line(12, '비가 왔다.')])

    assert history == lines[-HISTORY_LINES:]


# --- 프롬프트 ---

HISTORY = PersonHistory(
    entry_id=uuid.uuid4(),
    name='악역영애',
    lines=[line(3, '악역영애가 홍차를 건넸다.'), line(12, '악역영애가 경감에게 길을 알려 주었다.')],
)


def test_no_histories_leave_no_lines():
    assert prompt.history_lines([]) == []


def test_a_history_is_the_name_and_the_lines_with_their_rounds():
    assert prompt.history_lines([HISTORY]) == [
        prompt.HISTORY_TITLE,
        prompt.HISTORY_NOTE,
        '악역영애',
        '- (3 라운드) 악역영애가 홍차를 건넸다.',
        '- (12 라운드) 악역영애가 경감에게 길을 알려 주었다.',
        '',
    ]


def test_histories_come_after_the_memories_and_before_this_round():
    request = NarrationRequest(
        round_number=15,
        scene='리무진이 선다.',
        moves=[Move('모모', '다가간다.')],
        story=StoryContext(title='추격전', rating='all', guide=''),
        memories=[MemoryNote(round_number=3, text='결과: 홍차를 건넸다.')],
        histories=[HISTORY],
    )

    last = prompt.build_messages(request)[-1].content

    assert last.index(prompt.MEMORY_TITLE) < last.index(prompt.HISTORY_TITLE) < last.index('라운드에 한 일과 결과]')


def test_the_history_note_says_the_latest_is_closest_to_now():
    # 우호였다가 배신한 인물을 지금도 우호로 그리지 않게 한다
    assert '최근 일이 지금의 태도와 관계에 가깝다' in prompt.HISTORY_NOTE


# --- 테이블에서 ---


async def lady_note(app: FastAPI, table_id: uuid.UUID, name: str = '악역영애') -> LoreNote:
    """테이블의 복사본에서 악역영애 항목을 로어북 검색이 고른 모양으로. name 은 이름표다."""
    candidates = await load_candidates(app.state.session_factory, table_id)
    entry = next(item for item in candidates.entries if item.name == LADY['name'])
    return LoreNote(entry_id=entry.id, name=name, content=entry.content, kind=entry.kind)


def request_with(table_id: uuid.UUID | None, *notes: LoreNote, number: int = CURRENT) -> NarrationRequest:
    return NarrationRequest(round_number=number, scene='리무진이 선다.', moves=[], table_id=table_id, lore=list(notes))


async def test_a_person_picked_by_the_lore_gets_a_history(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table_id = await played_table(client, app, me)
    collector = HistoryCollector(app.state.session_factory)

    (history,) = await collector.find(request_with(table_id, await lady_note(app, table_id)))

    # 9 라운드를 서술할 때 6~8 라운드는 지난 기록에 있다. 2~5 라운드의 장면에서 악역영애가 나온 문장
    assert history.name == '악역영애'
    assert history.lines == [
        line(3, '악역영애가 부채를 접으며 웃었다.'),
        line(5, '악역영애가 은하 경찰에게 엘프가 간 길을 손짓으로 알려 주었다.'),
    ]


async def test_the_label_is_the_one_the_lore_chose(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table_id = await played_table(client, app, me)

    (history,) = await HistoryCollector(app.state.session_factory).find(
        request_with(table_id, await lady_note(app, table_id, name='영애'))
    )

    assert history.name == '영애'


async def test_too_early_a_round_has_no_history(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table_id = await played_table(client, app, me)
    note = await lady_note(app, table_id)

    # 5 라운드를 서술할 때 모을 수 있는 장면은 없다(2 라운드는 지난 기록에 든다). 빈 이력은 넣지 않는다
    assert await HistoryCollector(app.state.session_factory).find(request_with(table_id, note, number=5)) == []


async def test_only_people_get_a_history(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table_id = await played_table(client, app, me)
    lady = await lady_note(app, table_id)
    item = LoreNote(entry_id=lady.entry_id, name='리무진', content='', kind=LoreKind.ITEM)

    assert await HistoryCollector(app.state.session_factory).find(request_with(table_id, item)) == []


async def test_a_person_not_in_the_copy_is_skipped(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table_id = await played_table(client, app, me)
    stranger = LoreNote(entry_id=uuid.uuid4(), name='낯선 이', content='', kind=LoreKind.PERSON)

    assert await HistoryCollector(app.state.session_factory).find(request_with(table_id, stranger)) == []


async def test_at_most_a_few_people_get_a_history(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table_id = await played_table(client, app, me)
    lady = await lady_note(app, table_id)
    notes = [LoreNote(lady.entry_id, f'악역영애{number}', '', LoreKind.PERSON) for number in range(HISTORY_PEOPLE + 1)]

    histories = await HistoryCollector(app.state.session_factory).find(request_with(table_id, *notes))

    assert [history.name for history in histories] == [note.name for note in notes[:HISTORY_PEOPLE]]


async def test_no_table_or_no_people_means_no_history(app: FastAPI):
    collector = HistoryCollector(app.state.session_factory)
    note = LoreNote(uuid.uuid4(), '악역영애', '', LoreKind.PERSON)

    assert await collector.find(request_with(None, note)) == []
    assert await collector.find(request_with(uuid.uuid4())) == []
    assert await collector.find(request_with(uuid.uuid4(), note)) == []


# --- 라운드를 닫을 때 ---


async def test_closing_a_round_puts_the_history_in_the_prompt(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    provider = FakeProvider(reply='악역영애가 부채를 접으며 웃었다. 바람이 분다.')
    app.state.narrator = LLMNarrator(provider, DbCallLog(app.state.session_factory))
    table_url = await open_table(client, me, [LADY])

    # 선언에 악역영애가 나와 로어북이 그 항목을 고른다. 6 라운드를 서술할 때 처음으로 2 라운드의 장면을 모은다
    await play(client, app, me, table_url, ['달린다.'] * 5 + ['악역영애에게 손을 흔든다.'])

    last = provider.calls[-1].messages[-1].content
    assert prompt.HISTORY_TITLE in last
    assert '- (2 라운드) 악역영애가 부채를 접으며 웃었다.' in last
    assert '바람이 분다' not in last.split(prompt.HISTORY_TITLE)[1].split('라운드에 한 일과 결과]')[0]
    assert all(prompt.HISTORY_TITLE not in call.messages[-1].content for call in provider.calls[:5])
