# story-server/tests/test_summaries.py

"""
굴리는 요약의 규칙(app/memory/summaries.py). DB 도 모델도 쓰지 않는다.

보는 것.
  - 창 밖은 창(최근 말)에 들지 못한 앞부분이다
  - 마지막 요약 뒤에 밀려난 말이 기준보다 적으면 요약하지 않는다. 많으면 앞의 요약과 그 뒤의 말로 굴린다
  - 모델에 보낼 요약은 밀려난 말 가운데 가장 뒤의 것이다
  - 요약을 시키는 메시지에는 지시와, 앞의 줄거리(있으면), 말한 이의 이름을 붙인 이야기가 든다
"""

import uuid
from dataclasses import dataclass, field

from ai_core.provider import Role

from app.memory.summaries import Plan, latest_summary, overflow, plan_summary, render_story, summary_messages


@dataclass(frozen=True)
class Said:
    role: str
    content: str
    id: uuid.UUID = field(default_factory=uuid.uuid4)


PATH = [Said('assistant', 'a' * 400), Said('user', 'b' * 400), Said('assistant', 'c' * 400), Said('user', 'd' * 400)]


def test_the_overflow_is_what_the_window_leaves_out():
    assert overflow(PATH, 1000) == PATH[:2]
    assert overflow(PATH, 5000) == []


def test_too_few_new_messages_are_not_summarized():
    assert plan_summary(PATH[:2], {}, 3) is None
    assert plan_summary(PATH[:3], {PATH[0].id: '앞'}, 3) is None


def test_the_summary_rolls_from_the_last_one():
    plan = plan_summary(PATH, {PATH[1].id: '앞의 줄거리'}, 2)

    assert plan == Plan(previous='앞의 줄거리', fresh=PATH[2:])
    assert plan_summary(PATH, {}, 4) == Plan(previous=None, fresh=PATH)


def test_the_summary_sent_is_the_latest_in_the_overflow():
    summaries = {PATH[0].id: '처음', PATH[2].id: '나중'}

    assert latest_summary(PATH, summaries) == '나중'
    assert latest_summary(PATH[:2], summaries) == '처음'
    assert latest_summary(PATH, {}) is None


def test_the_request_has_the_instruction_the_story_and_the_speakers():
    plan = Plan(
        previous='둘은 처음 만났다.',
        fresh=[Said('user', '안녕'), Said('assistant', '@mina: 어서 와'), Said('action', '해변으로 갔다.')],
    )

    system, user = summary_messages(plan)

    assert system.role == Role.SYSTEM and '지어내지 않는다' in system.content
    assert user.content == (
        '[앞의 줄거리]\n둘은 처음 만났다.\n\n[이어진 이야기]\n'
        '사용자: 안녕\n이야기: @mina: 어서 와\n사용자의 행동: 해변으로 갔다.'
    )
    assert summary_messages(Plan(None, plan.fresh))[1].content.startswith('[이어진 이야기]')


def test_the_story_block():
    assert render_story('줄거리') == '[앞의 줄거리]\n줄거리'
    assert render_story(None) is None
