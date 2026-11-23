# shared/reference-core/tests/test_conversation_parts.py

"""
대화 서버(chat, story)가 쓰는 것을 검증한다.

  - 표의 칸(reference_core/columns.py): 서버가 물려받는 제약이 실제 DB 에서 걸린다
  - 남은 자리(selection.room_after): 로어북이 먼저다
  - 블록(prompt.py): 종류의 이름, 한국어 글, [상식]이 있을 때만 붙는 규칙
  - 찾기(finder.py): 자리가 없거나 글이 비면 읽지 않는다. 시간이 다 되거나 실패하면 빈 목록이다
  - 관리 명령(commands.py): 명령줄, 넣을 파일, 넣기와 색인의 결과의 줄
"""

import asyncio
import logging
import uuid
from pathlib import Path

import pytest
from ai_core.fake import FakeEmbedder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reference_core import commands, repository
from reference_core.data import DATA_FILES
from reference_core.finder import ReferenceFinder
from reference_core.loading import SyncPlan, load_document
from reference_core.prompt import CONVERSATION_NOTE, TITLE, TOPIC_RULE, kind_name, reference_line, render_references
from reference_core.records import ReferenceKind, ReferenceSource, StoredReference, write_document
from reference_core.selection import REFERENCE_MAX_CHARS, ReferenceThresholds, room_after
from tests.tables import TABLES, Entry
from tests.test_store import WIDE, document, record


def stored(key: str, kind: str = ReferenceKind.ITEM, **values) -> StoredReference:
    return StoredReference(id=uuid.uuid4(), key=key, name=key.title(), kind=kind, **values)


# --- 표의 칸 ---


async def test_the_inherited_constraints_hold(session: AsyncSession):
    session.add(Entry(source='nowhere', key='a', kind='item', name='A'))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_inherited_tables_take_a_line(session: AsyncSession):
    session.add(Entry(source='srd51', key='a', kind='topic', name='A', aliases=['가']))
    await session.commit()

    (line,) = await repository.list_stored(TABLES, session, ReferenceSource.SRD51)
    assert (line.key, line.aliases, line.content, line.name_ko) == ('a', ['가'], '', '')


# --- 남은 자리 ---


def test_the_room_is_what_the_lorebook_left():
    assert room_after(used=500, budget=2000) == REFERENCE_MAX_CHARS
    assert room_after(used=1200, budget=2000) == 800
    assert room_after(used=2500, budget=2000) == 0
    assert room_after(used=0, budget=2000, max_chars=300) == 300


# --- 블록 ---


def test_a_line_uses_the_korean_text_and_the_kind_name():
    line = stored('lich', kind=ReferenceKind.MONSTER, content='undead', name_ko='리치', content_ko='죽지 않는 마법사')

    assert reference_line(line) == '- [몬스터] 리치: 죽지 않는 마법사'
    assert kind_name('unknown') == 'unknown'


def test_the_block_adds_the_topic_rule_only_for_topics():
    item = stored('torch', content='탄다.')
    topic = stored('carrack', kind=ReferenceKind.TOPIC, content='돛대 셋')

    without = render_references([item])
    with_topic = render_references([item, topic])

    assert render_references([]) is None
    assert without is not None and with_topic is not None
    assert without == '\n'.join([TITLE, CONVERSATION_NOTE, '- [물건] Torch: 탄다.'])
    assert TOPIC_RULE in with_topic and TOPIC_RULE not in without
    assert with_topic.index(TOPIC_RULE) < with_topic.index('- [상식] Carrack: 돛대 셋')


# --- 찾기 ---


def finder(session_factory: async_sessionmaker[AsyncSession], embedder=None, **values) -> ReferenceFinder:
    return ReferenceFinder(
        TABLES, session_factory, embedder or FakeEmbedder(), operation='test.reference_find', thresholds=WIDE, **values
    )


async def test_the_finder_finds_by_alias(session_factory: async_sessionmaker[AsyncSession], session: AsyncSession):
    await load_document(TABLES, session, document(record('galleon', aliases=['갤리온'])))

    found = await finder(session_factory).find('갤리온이 보인다', room=1000)

    assert [line.key for line in found] == ['galleon']


async def test_the_finder_keeps_within_the_configured_chars(
    session_factory: async_sessionmaker[AsyncSession], session: AsyncSession
):
    await load_document(TABLES, session, document(record('galleon', aliases=['갤리온'], content='배' * 300)))
    small = ReferenceThresholds(max_distance=0.99, keyword_max_distance=1.0, max_chars=100)

    found = await ReferenceFinder(TABLES, session_factory, FakeEmbedder(), operation='test', thresholds=small).find(
        '갤리온', room=1000
    )

    assert found == []


class Never:
    """부르면 실패하는 세션 공장. 부르지 않았는지 본다."""

    def __call__(self):
        raise AssertionError('DB 를 읽었다')


async def test_the_finder_reads_nothing_without_room_or_text():
    never = finder(Never())  # type: ignore[arg-type]

    assert await never.find('갤리온', room=0) == []
    assert await never.find('   ', room=1000) == []


async def test_a_failure_is_logged_and_gives_nothing(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING):
        found = await finder(Never()).find('갤리온', room=1000)  # type: ignore[arg-type]

    assert found == []
    assert any(getattr(line, 'operation', None) == 'test.reference_find' for line in caplog.records)


class Slow:
    """답하지 않는 임베더."""

    model = 'slow'

    async def embed(self, texts: list[str]) -> list[list[float]]:
        await asyncio.sleep(10)
        return [[1.0] for _ in texts]


async def test_a_slow_search_gives_nothing(session_factory: async_sessionmaker[AsyncSession]):
    found = await finder(session_factory, embedder=Slow(), seconds=0.05).find('갤리온', room=1000)

    assert found == []


# --- 관리 명령 ---


def test_the_commands_are_read():
    parser = commands.build_parser()

    assert parser.parse_args(['load', 'srd51.json']).paths == [Path('srd51.json')]
    assert parser.parse_args(['load']).paths == []
    assert parser.parse_args(['index', '--model', 'bge-m3']).model == 'bge-m3'


def test_loading_without_files_takes_the_shipped_ones():
    assert commands.files_to_load([]) == list(DATA_FILES)
    assert commands.files_to_load([Path('a.json')]) == [Path('a.json')]


async def test_the_commands_report_what_they_did(session_factory: async_sessionmaker[AsyncSession], tmp_path: Path):
    first, second = tmp_path / 'a.json', tmp_path / 'b.json'
    write_document(document(record('galleon')), first)
    write_document(document(record('galleon')), second)

    loaded = await commands.load_files(TABLES, session_factory, [first, second])
    indexed = await commands.index(TABLES, session_factory, FakeEmbedder())
    again = await commands.index(TABLES, session_factory, FakeEmbedder(error='timeout'))

    assert loaded == (commands.DONE, ['srd51: 더함 1, 고침 0(벡터를 다시 만들 것 0), 지움 0', 'srd51: 바뀐 것이 없다'])
    assert indexed == (commands.DONE, ['모델 fake: 벡터 1개를 새로 만들었다'])
    assert again == (commands.DONE, ['모델 fake: 벡터 0개를 새로 만들었다'])


async def test_the_index_command_ends_with_one_when_vectors_are_left(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
):
    path = tmp_path / 'a.json'
    write_document(document(record('galleon')), path)
    await commands.load_files(TABLES, session_factory, [path])

    code, (line,) = await commands.index(TABLES, session_factory, FakeEmbedder(error='timeout'))

    assert code == commands.UNFINISHED
    assert '1개가 남았다' in line


def test_a_changed_plan_lists_the_counts():
    plan = SyncPlan(added=[], updated=[record('a')], reworded={'a'}, removed=[])

    assert commands.describe_plan('srd51', plan) == 'srd51: 더함 0, 고침 1(벡터를 다시 만들 것 1), 지움 0'


async def test_the_block_uses_what_the_lorebook_left(
    session_factory: async_sessionmaker[AsyncSession], session: AsyncSession
):
    await load_document(TABLES, session, document(record('galleon', aliases=['갤리온'], content='큰 배')))
    found = finder(session_factory)

    block = await found.block_after('갤리온', used=100, budget=2000)
    full = await found.block_after('갤리온', used=2000, budget=2000)

    assert block is not None and '- [물건] Galleon: 큰 배' in block
    assert full is None
