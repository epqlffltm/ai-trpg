# shared/ai-core/src/ai_core/catalog_contract.py

"""
모델 목록의 계약. AI 를 부르는 코드(ai_core)와 모델 목록을 들여오는 서비스가 함께 알아야 하는 것을 둔다
(#380, #496, #499).

  - 열거형: 모델을 부르는 창구(Provider), 생각을 켜고 끄는 방식(ReasoningStyle), 출력 상한의 칸(TokenLimitField),
    보이는 분류(Grade). 문자열 값은 DB 에 적힌 값과 같다. 바꾸지 않는다(마이그레이션과 표의 CHECK 가 이 값을 쓴다).
  - 값의 모양: 모델 하나(CatalogModel)와 그날의 원가 단가(UnitCost). 세션과 떨어진 바꾸지 못하는 값이다.
  - 읽는 쪽의 약속: 이름표로 모델을 찾는 것(ModelLookup). 어떻게 찾는지(DB, 캐시, 파일)는 모른다.
  - 순수 규칙: 생각을 끌 수 없는 모델인가(always_thinks), 그날 은퇴했나(is_retired), 그날 쓸 수 있나(is_offered),
    출력 상한의 칸과 생각의 방식이 창구에 맞나(token_field_problem, reasoning_style_problem).

모델 목록의 원본은 파일 하나다(ai_core/model_catalog.toml, 읽는 것은 ai_core/catalog_file.py).
서비스마다 그 파일을 자기 표에 들여오고, 켜고 끄기는 서비스의 표에서 한다(게임 서버는 trpg-server/app/catalog).
판매가와 고를 수 있는 모델(offers)은 서비스의 몫이라 여기 두지 않는다.
이 파일은 ai_core 밖의 app.* 를 가져오지 않는다. DB 를 모른다.
"""

import enum
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


class Provider(enum.StrEnum):
    """모델을 부르는 창구. 창구마다 부르는 코드가 따로 있다."""

    # OpenAI 의 API
    OPENAI = 'openai'
    # Anthropic 의 API(Claude)
    ANTHROPIC = 'anthropic'
    # Google 의 Gemini API
    GEMINI = 'gemini'
    # 서버 곁에서 도는 모델(Ollama, LM Studio). 설정의 LLM_BASE_URL 로 부른다
    LOCAL = 'local'
    # Z.ai 의 API(GLM). OpenAI 와 같은 모양이다. 출력 상한의 칸은 max_tokens 로 정해져 있다
    ZAI = 'zai'
    # DeepInfra 의 API(#398). 공개 가중치 모델(DeepSeek)을 미국에서 띄운 호스팅이다. OpenAI 와 같은 모양이다.
    # 출력 상한의 칸은 max_tokens 로 정해져 있고, 생각은 OpenAI 처럼 reasoning_effort 로 켜고 끈다(none 이면 꺼진다)
    DEEPINFRA = 'deepinfra'


class TokenLimitField(enum.StrEnum):
    """
    OpenAI 모양의 API 에서 출력 상한을 담는 칸의 이름. 모델마다 받는 칸이 다르다.

    서버 곁의 모델과 옛 모델은 max_tokens 를, OpenAI 의 생각하는 모델은 max_completion_tokens 만 받는다.
    Claude 와 Gemini 의 API 는 칸이 하나로 정해져 있어 적지 않는다.
    """

    MAX_TOKENS = 'max_tokens'
    MAX_COMPLETION_TOKENS = 'max_completion_tokens'


class ReasoningStyle(enum.StrEnum):
    """
    모델이 생각(thinking)을 켜고 끄는 방식. Claude 와 Gemini 의 모델마다 다르다(각 회사의 문서, 2026-10).

    서술은 생각을 꺼서 부른다(app/rounds/llm_narrator.py). 끄는 법과, 끌 수 없으면 어떻게 하는지가 모델마다 다르다.
    부르는 쪽(ai_core/anthropic.py, ai_core/gemini.py, ai_core/openai_compat.py)이 이 값을 보고 요청의 생각 칸을 만든다.
    창구마다 받는 값이 다르다(모델 목록을 읽을 때 STYLES_BY_PROVIDER 로 본다).
    budget 은 두 창구가 함께 쓴다.
    OpenAI 와 서버 곁의 모델은 이 칸을 쓰지 않는다(reasoning_effort 하나로 된다).
    끌 수 없는 방식(always, level_minimal, level_low, budget_min)의 모델은 판매가를 생각의 몫까지 넣어 매긴다.
    OpenAI 모양이어도 생각의 칸이 다른 창구(Z.ai)는 이 칸을 쓴다. 끌 수 있으면 thinking_type, 끌 수 없으면 always 다.
    """

    # 끌 수 있다(disabled). 켜면 스스로 깊이를 정한다(adaptive + effort). Opus 5, Sonnet 5, Haiku 5.5, Opus 4.6~4.8
    ADAPTIVE = 'adaptive'
    # 끌 수 없다. 끄라고 하면 effort 를 low 로 주고 출력 상한에 생각의 몫을 더한다. Opus 5.5, Fable 5.1·5
    ALWAYS = 'always'
    # disabled 를 받지 않는다. 미리 생각하지 않게 하는 between_tools 로 끈다. Sonnet 5.5
    BETWEEN_TOOLS = 'between_tools'
    # 켜면 생각의 토큰 상한을 준다. 끌 수 있다.
    # Claude 4.5 세대(enabled + budget_tokens, 끄기 disabled), Gemini 2.5 Flash·Flash-Lite(thinkingBudget, 끄기 0)
    BUDGET = 'budget'
    # Gemini 의 생각의 깊이(thinkingLevel). 끌 수 없다. 끄라고 하면 가장 낮은 minimal 로 준다.
    # minimal 도 생각을 끄는 것은 아니다. Gemini 3.6 Flash, 3.5·3.1 Flash-Lite, 3 Flash
    LEVEL_MINIMAL = 'level_minimal'
    # Gemini 의 생각의 깊이. 끌 수 없고 minimal 도 받지 않는다. 끄라고 하면 low 로 준다.
    # Gemini 4 Argon, 3.8 Flash, 3.1 Pro
    LEVEL_LOW = 'level_low'
    # Gemini 의 생각의 토큰 상한(thinkingBudget). 끌 수 없다. 끄라고 하면 가장 작은 128 로 준다. Gemini 2.5 Pro
    BUDGET_MIN = 'budget_min'
    # 생각을 thinking 칸({"type": "enabled" | "disabled"})으로 켜고 끈다. 끌 수 있다. Z.ai 의 GLM-4.7·4.6·5.1·5.2 등
    THINKING_TYPE = 'thinking_type'


class Grade(enum.StrEnum):
    """보이는 분류. 목록을 묶어 보이는 데만 쓴다. 값은 모델마다 모델 목록의 파일에 적는다."""

    # 아주 싸거나 행사로 풀 모델. 서버 곁의 모델로 한다
    BASIC = 'basic'
    STANDARD = 'standard'
    # 비싼 모델(Opus, Fable, Astra, Argon)
    PREMIUM = 'premium'


# 생각을 끌 수 없는 방식들. 이 모델들은 판매가를 생각의 몫까지 넣어 매긴다(유저 결정, model-pricing-plan 9-2)
ALWAYS_THINKING = frozenset(
    {ReasoningStyle.ALWAYS, ReasoningStyle.LEVEL_MINIMAL, ReasoningStyle.LEVEL_LOW, ReasoningStyle.BUDGET_MIN}
)


@dataclass(frozen=True)
class UnitCost:
    """그날의 원가 단가(USD, 백만 토큰당). cost_id 는 그 단가의 줄(ai_model_costs.id)이다. 캐시 단가는 없을 수 있다."""

    cost_id: int
    input_per_mtok: Decimal
    output_per_mtok: Decimal
    cached_input_per_mtok: Decimal | None = None
    cache_write_per_mtok: Decimal | None = None


@dataclass(frozen=True)
class CatalogModel:
    """모델 목록의 모델 하나. 부를 때 필요한 것만 담은 값이다. cost 는 찾은 날의 단가다(없으면 None)."""

    slug: str
    provider: Provider
    api_model_id: str
    supports_reasoning: bool
    supports_temperature: bool
    token_limit_field: TokenLimitField | None
    enabled: bool
    retires_on: date | None
    cost: UnitCost | None = None
    reasoning_style: ReasoningStyle | None = None


class ModelLookup(Protocol):
    """이름표로 모델을 찾는 것의 모양."""

    async def find(self, slug: str, day: date) -> CatalogModel | None:
        """그 이름표의 모델과 그날의 단가. 목록에 없으면 None."""
        ...


class Switchable(Protocol):
    """켜짐과 은퇴일이 있는 것. 모델의 ORM 객체(app/catalog 의 AiModel)와 찾은 값(CatalogModel)이 맞는다."""

    @property
    def enabled(self) -> bool: ...

    @property
    def retires_on(self) -> date | None: ...


def always_thinks(style: ReasoningStyle | None) -> bool:
    """생각을 끌 수 없는 모델인가. 판매가와 출력 상한에 생각의 몫을 넣는다."""
    return style in ALWAYS_THINKING


def is_retired(model: Switchable, today: date) -> bool:
    """그날 은퇴했나. 은퇴일 당일부터 은퇴다."""
    return model.retires_on is not None and today >= model.retires_on


def is_offered(model: Switchable, today: date) -> bool:
    """그날 쓸 수 있나. 켜져 있고 은퇴하지 않았다."""
    return model.enabled and not is_retired(model, today)


# 출력 상한의 칸을 적어야 하는 창구. OpenAI 모양의 API 다. 나머지 창구는 칸이 정해져 있어 적지 않는다
TOKEN_FIELD_PROVIDERS = frozenset({Provider.OPENAI, Provider.LOCAL})

# 생각을 켜고 끄는 방식을 적어야 하는 창구와, 그 창구가 받는 방식들. 모델마다 방식이 다르다
STYLES_BY_PROVIDER = {
    Provider.ANTHROPIC: frozenset(
        {ReasoningStyle.ADAPTIVE, ReasoningStyle.ALWAYS, ReasoningStyle.BETWEEN_TOOLS, ReasoningStyle.BUDGET}
    ),
    Provider.GEMINI: frozenset(
        {ReasoningStyle.LEVEL_MINIMAL, ReasoningStyle.LEVEL_LOW, ReasoningStyle.BUDGET, ReasoningStyle.BUDGET_MIN}
    ),
    # 끌 수 있으면 thinking 칸으로 끈다. 끌 수 없는 모델(GLM-5.3 계열)은 칸을 보내지 않고 생각의 몫을 더한다
    Provider.ZAI: frozenset({ReasoningStyle.THINKING_TYPE, ReasoningStyle.ALWAYS}),
}


def token_field_problem(provider: Provider, field: TokenLimitField | None) -> str | None:
    """출력 상한의 칸이 창구에 맞지 않으면 그 까닭, 맞으면 None."""
    if provider in TOKEN_FIELD_PROVIDERS and field is None:
        return f'{provider} 창구의 모델은 출력 상한의 칸(max_tokens, max_completion_tokens)을 적어야 한다'
    if provider not in TOKEN_FIELD_PROVIDERS and field is not None:
        return f'{provider} 창구의 모델은 출력 상한의 칸을 적지 않는다'
    return None


def styles_text(provider: Provider) -> str:
    """그 창구가 받는 방식들을 글로(안내에 쓴다)."""
    return ', '.join(sorted(STYLES_BY_PROVIDER[provider]))


def reasoning_style_problem(provider: Provider, style: ReasoningStyle | None) -> str | None:
    """생각을 켜고 끄는 방식이 창구에 맞지 않으면 그 까닭, 맞으면 None."""
    if provider not in STYLES_BY_PROVIDER:
        return None if style is None else f'{provider} 창구의 모델은 생각을 켜고 끄는 방식을 적지 않는다'
    if style is None:
        return f'{provider} 창구의 모델은 생각을 켜고 끄는 방식({styles_text(provider)})을 적어야 한다'
    if style not in STYLES_BY_PROVIDER[provider]:
        return f'{provider} 창구가 받는 생각의 방식이 아니다({styles_text(provider)} 중 하나)'
    return None
