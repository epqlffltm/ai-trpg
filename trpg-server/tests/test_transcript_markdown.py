# trpg-server/tests/test_transcript_markdown.py

"""
이벤트를 기록의 글로 바꾸는 것(#403, app/transcripts/markdown.py)을 검증한다. DB 를 쓰지 않는다.

보는 것.
  - 쓰는 종류는 모두 글이 된다. 어느 글에도 내부 식별자(UUID)가 남지 않는다.
  - 쓰지 않는 종류(쪽지, 설정, 서술 실패)는 빈 글자다. 숨긴 퀘스트도 쓰지 않는다.
  - 앉은 사람에게 보이지 않는 칸은 payload 에 있어도 쓰지 않는다.
  - 능력치, 난이도, 부상은 판의 규칙에 적힌 이름으로 쓴다. 없으면 이름표 그대로다.
  - 서술과 선언의 글이 파일의 제목처럼 보이지 않는다(맨 앞의 # 을 글자로 남긴다).
  - 머리에 제목과 범위가 있다. 떠난 사람의 것이면 "떠난 때까지"다.
"""

import re
import uuid
from datetime import UTC, datetime

import pytest

from app.events.models import EventType, TableEvent
from app.transcripts.labels import Labels
from app.transcripts.markdown import RENDERERS, header, render, render_event, scenes_under_rounds
from app.transcripts.reading import Cut
from tests.transcript_samples import SAMPLES

UUID_PATTERN = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
LABELS = Labels(abilities={'dex': '민첩'}, difficulties={'medium': '보통'}, injuries={'lost_eye': '한쪽 눈 잃음'})


def event(type_: str, payload: dict) -> TableEvent:
    return TableEvent(type=type_, payload=payload, sequence=1)


def cut(departed: bool) -> Cut:
    return Cut(table_id=uuid.uuid4(), title='추격전', until=42, departed=departed, labels=Labels())


def test_every_written_kind_has_a_sample():
    assert {EventType(name) for name in SAMPLES} == set(RENDERERS)


@pytest.mark.parametrize('type_', list(SAMPLES))
def test_every_written_kind_becomes_text_without_ids(type_: str):
    text = render_event(event(type_, SAMPLES[type_]), LABELS)

    assert text.strip()
    assert UUID_PATTERN.search(text) is None


@pytest.mark.parametrize(
    'type_',
    [EventType.WHISPER_SENT, EventType.NARRATION_FAILED, EventType.NARRATION_MODEL_CHANGED, EventType.ROUND_CLOSED],
)
def test_kinds_outside_the_story_are_left_out(type_: EventType):
    payload = {'user_id': str(uuid.uuid4()), 'character_name': '엘프', 'recipient_character_name': '영애', 'round': 1}

    assert render_event(event(type_, payload), LABELS) == ''


def test_a_hidden_quest_is_left_out():
    payload = {**SAMPLES['quest_changed'], 'previous': None, 'status': 'hidden'}

    assert render_event(event('quest_changed', payload), LABELS) == ''


def test_fields_hidden_from_players_are_not_written():
    # NPC 의 HP 숫자와 몸 상태는 GM 만 안다. payload 에 있어도 앉은 사람에게 보이는 칸이 아니다
    payload = {**SAMPLES['npc_changed'], 'before': 31, 'after': 28, 'max_hp': 40, 'condition': '왼팔을 감싸 쥔다'}

    text = render_event(event('npc_changed', payload), LABELS)

    assert '31' not in text and '40' not in text and '왼팔' not in text


def test_the_rules_give_the_names():
    text = render_event(event('check_rolled', SAMPLES['check_rolled']), LABELS)
    unnamed = render_event(event('check_rolled', SAMPLES['check_rolled']), Labels())

    assert text == '- 판정: 엘프 · 민첩(보통) 20 + 0 = 20, 목표 20 → 성공\n'
    assert '· dex(medium)' in unnamed


def test_the_main_lines_read_as_a_story():
    assert (
        render_event(event('round_opened', SAMPLES['round_opened']), LABELS) == '\n## 라운드 1 · 1일째 08:00(아침)\n\n'
    )
    assert render_event(event('player_action', SAMPLES['player_action']), LABELS) == (
        '\n> **엘프**\n> 악역영애에게 주먹을 날린다.\n\n'
    )
    assert render_event(event('hp_changed', SAMPLES['hp_changed']), LABELS) == '- 엘프: 피해 16 (HP 10 → 0), 쓰러짐\n'
    assert render_event(event('injury_gained', SAMPLES['injury_gained']), LABELS) == '- 부상: 악역영애 · 한쪽 눈 잃음\n'
    assert render_event(event('character_moved', SAMPLES['character_moved']), LABELS) == (
        '- 이동: 드워프 기사 · 수로 입구 → 깊은 수로\n'
    )


def test_written_text_does_not_make_headings():
    narration = {'text': '# 제목인 척\n\n문을 연다.\n## 또 하나'}
    action = {'character_name': '엘프', 'content': '# 외친다'}

    told = render_event(event('gm_narration', narration), LABELS)
    declared = render_event(event('player_action', action), LABELS)

    assert told == '\n\\# 제목인 척\n\n문을 연다.\n\\## 또 하나\n\n'
    assert '> \\# 외친다' in declared


def test_a_missing_name_is_said_plainly():
    assert render_event(event('member_left', {'character_name': None}), LABELS) == '- 이름 없는 사람: 테이블을 나감\n'


@pytest.mark.parametrize(('departed', 'scope'), [(False, '1~42번 이벤트'), (True, '1~42번 이벤트 (떠난 때까지)')])
def test_the_header_names_the_table_and_the_scope(departed: bool, scope: str):
    text = header(cut(departed), datetime(2026, 10, 20, 12, 0, tzinfo=UTC))

    assert text == f'# 추격전\n\n- 기록: {scope}\n- 내려받은 때: 2026-10-20T12:00:00+00:00\n\n'


async def test_the_round_comes_before_the_scene_it_opens():
    written = [
        'table_started',
        'gm_narration',
        'round_opened',
        'player_action',
        'check_rolled',
        'gm_narration',
        'injury_ended',
        'round_opened',
        'gm_narration',
        'table_ended',
    ]

    async def stored():
        for number, type_ in enumerate(written, start=1):
            yield TableEvent(type=type_, payload={}, sequence=number)

    shown = [one.sequence async for one in scenes_under_rounds(stored())]

    # 서술(2)이 여는 라운드(3)가 먼저, 결과의 서술(6)과 그 사이의 일(7)은 2 라운드(8) 뒤로. 마지막 서술은 그대로다
    assert shown == [1, 3, 2, 4, 5, 8, 6, 7, 9, 10]


async def test_pieces_are_kept_apart_by_one_blank_line():
    written = [
        ('round_opened', SAMPLES['round_opened']),
        ('check_rolled', SAMPLES['check_rolled']),
        ('gm_narration', {'text': '문을 연다.'}),
        ('player_action', {'character_name': '엘프', 'content': '달린다.'}),
        ('player_action', {'character_name': '영애', 'content': '웃는다.'}),
    ]

    async def stored():
        for number, (type_, payload) in enumerate(written, start=1):
            yield TableEvent(type=type_, payload=payload, sequence=number)

    text = ''.join([piece async for piece in render(cut(departed=False), stored())])

    assert '\n\n\n' not in text
    # 목록 뒤의 문단은 빈 줄로 떼고(목록에 붙지 않게), 인용 둘도 빈 줄로 뗀다(하나로 합쳐지지 않게)
    assert '목표 20 → 성공\n\n문을 연다.\n\n> **엘프**\n> 달린다.\n\n> **영애**' in text
