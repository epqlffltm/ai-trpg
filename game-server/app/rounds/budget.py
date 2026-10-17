# game-server/app/rounds/budget.py

"""
서술 요청의 입력 토큰 예산. 판매가가 가정한 입력(ROUND_INPUT_TOKENS, 12,000 토큰)을 넘지 않게 한다.

판매가는 "한 라운드에 입력 12,000, 출력 1,200 토큰"으로 매겼다(app/catalog/rules.py, 결제 서버의 가격표).
보내는 양이 그보다 많으면 그 라운드는 판 값보다 원가가 크다.

세는 법: 글자 수 × TOKENS_PER_CHAR 로 어림한다(유저 결정, 2026-10-18).
  - 공급자마다 토크나이저가 달라 한글 한 글자가 몇 토큰인지 다르다(대략 0.5~1.5).
    창구마다 토크나이저 코드를 두거나 부를 때마다 세기 API 를 부르지 않는다.
  - 대신 판매가의 70% 까지만 보낸다(INPUT_BUDGET). 어림이 30% 쯤 틀려도 판매가 안이다.
  - 호출 기록에 보낸 글자 수(input_chars)를 남긴다. 실제 입력 토큰 수와 견주어 비율과 여유를 고친다.
    올리는 쪽은 안전하다. 이미 매긴 판매가는 그대로다. 그래서 코드의 상수로 두고 PR 로 바꾼다.

넘치면 덜 중요한 것부터 뺀다(fit_request).
  1. 지난 기록(대화로 넣는 최근 라운드)의 오래된 것부터
  2. 로어북 항목의 덜 가까운 것부터(검색이 고른 순서의 뒤에서)
  3. 지난 일(기억)의 덜 가까운 것부터
  빼지 않는 것: 시스템 지시(규칙, 작가의 글), 바로 앞 장면, 이번 라운드의 선언과 결과, 상태, 맵, 몬스터.
  엔진이 정한 사실과 작가의 글이다. 빼면 서술이 틀어지고, 작가의 글을 중간에서 자르면 세계관이 끊긴다.

다 빼고도 넘치는 것은 빼지 않는 것이 큰 때다. 그래도 부른다. 라운드를 실패시키면 앉은 사람 모두가 멈춘다.
작가의 글이 판매가의 예산을 혼자 넘는 판은 테이블을 시작할 때 막는다(story_fits, app/tables/service.py).
"""

import math
from collections.abc import Iterator
from dataclasses import replace

from app.ai.calls import chars_of
from app.ai.provider import ChatMessage
from app.assets.models import NarrationStyle
from app.catalog.rules import ROUND_INPUT_TOKENS
from app.rounds.narrator import NarrationRequest, StoryContext
from app.rounds.prompt import HISTORY_MAX_CHARS, HISTORY_ROUNDS, build_messages, fit_history, system_text

# 글자 하나를 몇 토큰으로 어림하나. 호출 기록(input_chars, input_tokens)으로 고친다
TOKENS_PER_CHAR = 1.0
# 판매가가 가정한 입력 중 실제로 보내는 몫. 어림이 틀려도 판매가를 넘지 않게 남겨 둔다
INPUT_SAFETY_RATIO = 0.7
# 서술 요청에 보내는 입력의 상한(어림 토큰)
INPUT_BUDGET = int(ROUND_INPUT_TOKENS * INPUT_SAFETY_RATIO)
# 시스템 지시(규칙과 작가의 글)의 상한(어림 토큰). 이보다 크면 어느 라운드든 판매가를 넘는다
STORY_MAX_TOKENS = ROUND_INPUT_TOKENS


def estimate_tokens(chars: int) -> int:
    """글자 수로 어림한 토큰 수. 올림한다."""
    return math.ceil(chars * TOKENS_PER_CHAR)


def estimate_messages(messages: list[ChatMessage]) -> int:
    """메시지들의 어림 토큰 수."""
    return estimate_tokens(chars_of(messages))


def story_tokens(story: StoryContext, style: NarrationStyle) -> int:
    """시스템 지시(규칙, 문체, 수위, 작가의 글)의 어림 토큰 수. 라운드마다 똑같이 들어가는 몫이다."""
    return estimate_tokens(len(system_text(story, style)))


def story_fits(story: StoryContext, style: NarrationStyle) -> bool:
    """작가의 글이 판매가의 입력 예산 안에 드나. 안 들면 테이블을 시작하지 않는다."""
    return story_tokens(story, style) <= STORY_MAX_TOKENS


def trimmed(request: NarrationRequest) -> Iterator[NarrationRequest]:
    """
    요청을 하나씩 줄여 가며 내놓는다. 처음 것은 줄이지 않은 요청이다(지난 기록의 글자 수 상한만 건 것).

    지난 기록의 오래된 것 → 로어북 항목의 뒤쪽 → 기억의 뒤쪽 순서로 하나씩 뺀다. 마지막 것은 셋을 다 뺀 요청이다.
    """
    current = replace(request, history=fit_history(request.history, HISTORY_ROUNDS, HISTORY_MAX_CHARS))
    yield current
    while current.history:
        current = replace(current, history=current.history[1:])
        yield current
    while current.lore:
        current = replace(current, lore=current.lore[:-1])
        yield current
    while current.memories:
        current = replace(current, memories=current.memories[:-1])
        yield current


def fit_request(request: NarrationRequest, budget: int = INPUT_BUDGET) -> NarrationRequest:
    """
    입력이 budget(어림 토큰) 안에 드는 가장 덜 줄인 요청. 다 줄여도 안 들면 다 줄인 요청이다.

    이야기의 바탕(request.story)이 있어야 한다(build_messages).
    """
    last = request
    for candidate in trimmed(request):
        last = candidate
        if estimate_messages(build_messages(candidate)) <= budget:
            return candidate
    return last
