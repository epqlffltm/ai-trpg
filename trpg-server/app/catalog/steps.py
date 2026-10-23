# trpg-server/app/catalog/steps.py

"""
서술의 입력·출력 단계(#387). 테이블이 고르는 "한 라운드에 얼마나 보내고 얼마나 받는가"다. DB 도 HTTP 도 모른다.

  - 입력 단계 0~2: 한 단계마다 입력 +8,000 토큰. 12,000, 20,000, 28,000
  - 출력 단계 0~2: 한 단계마다 출력 +1,000 토큰. 1,200, 2,200, 3,200
  (모델별 과금표 v0.1 의 옵션, 프로젝트 문서 model-pricing-plan 1절)
가격표 이름의 끝(narration.<이름표>.i<입력>.o<출력>)이 단계다. 값은 결제 서버의 가격표가 정한다.

단계가 오르면 서술에 넣는 것의 칸마다의 상한도 함께 는다(유저 결정, 2026-10-23). 예산만 키우면 칸의 상한에 막혀
늘어난 값이 서술에 들어가지 않는다.
  - 글자 수의 상한(지난 기록, 로어북, 기억, 참고 자료): 입력 토큰과 같은 비율로(1, 5/3, 7/3 배)
  - 개수의 상한(지난 기록의 라운드 수, 기억의 수): 단계마다 처음 값만큼 더한다(3, 6, 9 라운드)
출력 단계는 장면의 길이 안내와 받는 장면의 상한을 정한다(app/rounds/prompt.py, app/rounds/llm_narrator.py).
"""

from dataclasses import dataclass
from typing import Protocol

# 기본 단계(i0.o0)에서 1라운드를 어림하는 토큰 수. 판매가를 정할 때 쓴 값과 같다(프로젝트 문서 model-pricing-plan)
ROUND_INPUT_TOKENS = 12_000
ROUND_OUTPUT_TOKENS = 1_200
# 가장 높은 단계. 입력과 출력이 같다
MAX_STEP = 2
# 한 단계마다 더하는 토큰
INPUT_STEP_TOKENS = 8_000
OUTPUT_STEP_TOKENS = 1_000


@dataclass(frozen=True)
class NarrationSteps:
    """입력 단계와 출력 단계. 둘 다 0 이상 MAX_STEP 이하다. 아니면 ValueError."""

    input: int = 0
    output: int = 0

    def __post_init__(self) -> None:
        for step in (self.input, self.output):
            if not 0 <= step <= MAX_STEP:
                raise ValueError(f'단계는 0 부터 {MAX_STEP} 까지다: {step}')


# 기본 단계. 판매가를 처음 매긴 i0.o0 이다
BASE_STEPS = NarrationSteps()
# 모든 단계의 조합. 입력, 출력 순서다
ALL_STEPS = tuple(NarrationSteps(i, o) for i in range(MAX_STEP + 1) for o in range(MAX_STEP + 1))


class HasSteps(Protocol):
    """단계를 칸으로 가진 것. 테이블(GameTable)과 라운드(Round)다."""

    input_step: int
    output_step: int


def steps_of(row: HasSteps) -> NarrationSteps:
    """테이블이나 라운드의 단계."""
    return NarrationSteps(row.input_step, row.output_step)


def input_tokens(steps: NarrationSteps) -> int:
    """그 단계에서 판매가가 가정한 한 라운드의 입력 토큰."""
    return ROUND_INPUT_TOKENS + INPUT_STEP_TOKENS * steps.input


def output_tokens(steps: NarrationSteps) -> int:
    """그 단계에서 판매가가 가정한 한 라운드의 출력 토큰. 서술을 부를 때의 출력 상한이다."""
    return ROUND_OUTPUT_TOKENS + OUTPUT_STEP_TOKENS * steps.output


def scaled_chars(chars: int, steps: NarrationSteps) -> int:
    """기본 단계의 글자 수 상한을 그 단계의 것으로. 입력 토큰과 같은 비율이다. 내림한다."""
    return chars * input_tokens(steps) // ROUND_INPUT_TOKENS


def scaled_count(count: int, steps: NarrationSteps) -> int:
    """기본 단계의 개수 상한을 그 단계의 것으로. 단계마다 처음 값만큼 더한다."""
    return count * (1 + steps.input)


def steps_code(steps: NarrationSteps) -> str:
    """가격표 이름의 끝. 예: i1.o0"""
    return f'i{steps.input}.o{steps.output}'
