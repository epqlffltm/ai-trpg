# game-server/tests/test_truncated_narration.py

"""
출력 상한에 걸려 잘린 서술을 받는 것(app/rounds/llm_narrator.py 의 accept_truncated)을 검증한다.

보는 것.
  - 마지막으로 끝난 문장까지만 남긴다. 닫는 따옴표와 괄호는 문장에 붙여 둔다.
  - 그렇게 남은 글이 너무 짧으면 받지 않는다(cut_off). 같은 모델로 다시 부르게 된다.
  - 잘라 받은 호출도 기록에 남는다. 끝난 까닭(finish_reason)으로 잘렸다는 것을 안다.
"""

import pytest

from app.ai.calls import Outcome
from app.ai.fake import FAKE_MODEL, FakeCallLog, FakeProvider
from app.ai.provider import Completion
from app.rounds.llm_narrator import (
    TRUNCATED_MIN_LENGTH,
    LLMNarrator,
    NarrationError,
    accept_completion,
    trim_to_sentence,
)
from tests.test_llm_narrator import make_request

# 끝난 문장 몇 개와, 상한에 걸려 중간에서 끊긴 문장 하나
SENTENCE = '비에 젖은 간판이 깜박였고, 골목 끝에서 누군가 우산을 접었다. '
WHOLE = SENTENCE * 12
CUT = WHOLE + '그때 경적이 울리며'


@pytest.mark.parametrize(
    ('text', 'kept'),
    [
        ('문을 열었다. 바람이 불', '문을 열었다.'),
        ('"누구냐!" 경비가 외쳤', '"누구냐!"'),
        ('그는 웃었다…… 그리고', '그는 웃었다……'),
        ('정말 그럴까? 아무도 몰랐', '정말 그럴까?'),
        ('「멈춰라.」 목소리가', '「멈춰라.」'),
        ('끝난 문장이 없는 글', ''),
    ],
)
def test_only_the_finished_sentences_are_kept(text: str, kept: str):
    assert trim_to_sentence(text) == kept


def test_a_long_cut_reply_is_kept_up_to_its_last_sentence():
    scene = accept_completion(Completion(text=CUT, model=FAKE_MODEL, truncated=True))

    # 문장 중간에서 끊긴 글은 굳지 않는다. 다시 부르지 않으니 값을 한 번 더 내지 않는다
    assert scene == WHOLE.strip()
    assert '경적' not in scene


@pytest.mark.parametrize('text', ['', '문을 열었다. 바람이 불', SENTENCE[:-1] * 2 + '끊긴'])
def test_a_short_cut_reply_is_not_a_scene(text: str):
    assert len(trim_to_sentence(text)) < TRUNCATED_MIN_LENGTH

    # 생각을 끌 수 없는 모델이 생각에 출력을 다 써서 본문이 거의 없는 경우다. 다시 부른다
    with pytest.raises(NarrationError, match='cut_off'):
        accept_completion(Completion(text=text, model=FAKE_MODEL, truncated=True))


def test_a_cut_reply_that_is_still_too_long_is_not_a_scene():
    with pytest.raises(NarrationError, match='too_long'):
        accept_completion(Completion(text=SENTENCE * 200, model=FAKE_MODEL, truncated=True))


async def test_a_reply_kept_up_to_its_last_sentence_is_recorded_as_used(caplog):
    log = FakeCallLog()

    with caplog.at_level('WARNING', logger='app.rounds.llm_narrator'):
        scene = await LLMNarrator(FakeProvider(reply=CUT, truncated=True), log).narrate(make_request())

    (record,) = log.records
    # 쓴 호출이다. 원문은 그대로 남아 어디서 잘렸는지 볼 수 있다
    assert scene == WHOLE.strip()
    assert (record.outcome, record.error, record.text) == (Outcome.OK, None, CUT)
    assert any(getattr(entry, 'result', None) == 'truncated' for entry in caplog.records)
