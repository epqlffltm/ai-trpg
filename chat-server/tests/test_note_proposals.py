# chat-server/tests/test_note_proposals.py

"""
요약이 기억 메모를 제안하는 규칙(app/memory/summaries.py, #677)을 검증한다. DB 도 모델도 쓰지 않는다.

보는 것.
  - 줄거리와 표식 뒤의 제안을 가른다. 표식이 없으면 제안이 없다. 닫는 태그 뒤는 버린다
  - 제안 줄에서 번호와 글머리표, 따옴표를 뗀다
  - 빈 것, 긴 것, 이미 있는 것(빈칸과 대소문자를 가리지 않는다), 겹치는 것을 뺀다
  - 한 번에 셋까지다
  - 요약을 시키는 메시지에 표식의 지시와 이미 적힌 기억이 들어간다
"""

import uuid
from dataclasses import dataclass

from app.memory.models import NOTE_MAX_CHARS
from app.memory.summaries import NOTES_MARKER, Plan, pick_proposals, split_summary, summary_messages


@dataclass(frozen=True)
class Said:
    id: uuid.UUID
    role: str
    content: str


def test_the_story_and_the_proposals_are_split():
    story, lines = split_summary('비가 왔다.\n<notes>\n- 고양이를 좋아한다\n2. 3월생이다\n</notes>\n덤')

    assert story == '비가 왔다.'
    assert [line for line in lines if line.strip()] == ['- 고양이를 좋아한다', '2. 3월생이다']


def test_without_the_marker_there_are_no_proposals():
    assert split_summary('  비가 왔다.  ') == ('비가 왔다.', [])


def test_proposals_are_cleaned_and_filtered():
    lines = [
        '- "고양이를 좋아한다"',
        '',
        '1) 3월생이다',
        'x' * (NOTE_MAX_CHARS + 1),
        '  고양이를   좋아한다 ',
        '커피는 싫다',
    ]

    assert pick_proposals(lines, ['커피는 싫다']) == ['고양이를 좋아한다', '3월생이다']


def test_known_notes_are_matched_without_case_or_spacing():
    assert pick_proposals(['Likes  CATS'], ['likes cats']) == []


def test_at_most_three_are_proposed():
    assert pick_proposals(['하나', '둘', '셋', '넷'], []) == ['하나', '둘', '셋']


def test_the_summary_request_shows_the_known_notes_and_the_marker():
    plan = Plan(previous='앞의 일.', fresh=[Said(uuid.uuid4(), 'user', '안녕')], known=('고양이를 좋아한다',))

    system, user = summary_messages(plan)

    assert NOTES_MARKER in system.content
    assert user.content.startswith('[이미 적힌 기억]\n- 고양이를 좋아한다\n\n[앞의 줄거리]\n앞의 일.')


def test_without_known_notes_there_is_no_block():
    plan = Plan(previous=None, fresh=[Said(uuid.uuid4(), 'user', '안녕')])

    assert '[이미 적힌 기억]' not in summary_messages(plan)[1].content
