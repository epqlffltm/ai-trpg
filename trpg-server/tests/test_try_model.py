# trpg-server/tests/test_try_model.py

"""
모델 하나를 불러 보는 명령(scripts/try_model.py)을 검증한다.

실제 모델을 부르지 않는다. httpx 의 가짜 전송이 OpenAI 인 척 답한다. 모델 목록은 사전으로 흉내 낸다.
꺼진 모델도 부르는 것, 은퇴한 모델은 부르지 않는 것, 실패하면 까닭만 찍고 키는 찍지 않는 것을 본다.
"""

import json
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

import httpx
from pydantic import SecretStr

from app.ai.calls import chars_of
from app.ai.catalog_contract import CatalogModel, Provider, TokenLimitField, UnitCost
from app.ai.provider import ChatMessage, GenerationParams, Reasoning, Role
from app.ai.routing import Endpoint, ModelRouter
from scripts.try_model import (
    DEFAULT_MAX_TOKENS,
    MESSAGES,
    build_parser,
    messages_of,
    params_of,
    read_text,
    try_once,
)

TODAY = date(2026, 10, 17)
KEY = 'sk-test'
LUNA = CatalogModel(
    slug='gpt-6-luna',
    provider=Provider.OPENAI,
    api_model_id='gpt-6-luna-2026-09-22',
    supports_reasoning=True,
    supports_temperature=True,
    token_limit_field=TokenLimitField.MAX_COMPLETION_TOKENS,
    enabled=False,
    retires_on=None,
)
PARAMS = GenerationParams(max_tokens=DEFAULT_MAX_TOKENS, temperature=0.8)


@dataclass
class OneModel:
    """모델 하나만 든 목록."""

    model: CatalogModel

    async def find(self, slug: str, day: date) -> CatalogModel | None:
        return self.model if slug == self.model.slug else None


def answer(status: int = 200) -> httpx.MockTransport:
    """글 두 조각과 토큰 수를 흘려 보내는 답. status 가 200 이 아니면 그 상태로 답한다."""
    pieces = [
        {'model': 'gpt-6-luna-2026-09-22', 'choices': [{'index': 0, 'delta': {'content': '사이렌이 '}}]},
        {'model': 'gpt-6-luna-2026-09-22', 'choices': [{'index': 0, 'delta': {'content': '울린다.'}}]},
        {'model': 'gpt-6-luna-2026-09-22', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]},
        {'model': 'gpt-6-luna-2026-09-22', 'choices': [], 'usage': {'prompt_tokens': 60, 'completion_tokens': 9}},
    ]
    text = ''.join(f'data: {json.dumps(piece, ensure_ascii=False)}\n\n' for piece in pieces) + 'data: [DONE]\n\n'
    body = text if status == 200 else f'{{"error": "{KEY} is wrong"}}'
    return httpx.MockTransport(lambda request: httpx.Response(status, text=body))


def router_with(model: CatalogModel, transport: httpx.MockTransport) -> ModelRouter:
    """그 모델 하나가 든 목록으로 고르는 것."""
    return ModelRouter(
        lookup=OneModel(model),
        client=httpx.AsyncClient(transport=transport),
        local=Endpoint('http://127.0.0.1:11434/v1', None, 'openai_compat'),
        openai=Endpoint('https://api.openai.com/v1', SecretStr(KEY), 'openai'),
        timeout=30,
        today=lambda: TODAY,
    )


async def test_a_disabled_model_is_called_and_summarised():
    pieces: list[str] = []

    code, lines = await try_once(router_with(LUNA, answer()), 'gpt-6-luna', PARAMS, pieces.append)

    # 켜기 전에 불러 보는 것이라 꺼진 모델도 부른다. 글은 오는 대로 넘긴다
    assert code == 0
    assert pieces == ['사이렌이 ', '울린다.']
    assert lines[1] == '창구 openai, 답한 모델 gpt-6-luna-2026-09-22, 멈춘 이유 stop'
    assert lines[2] == '토큰: 입력 60(캐시 모름), 출력 9(생각 모름)'
    assert lines[3] == '원가: 오늘의 단가가 없다(scripts.models set-cost)'
    assert lines[4].startswith('시간: 첫 글 ')


async def test_a_retired_model_is_not_called():
    retired = replace(LUNA, retires_on=TODAY)

    code, lines = await try_once(router_with(retired, answer()), 'gpt-6-luna', PARAMS, lambda piece: None)

    assert (code, lines) == (1, ['gpt-6-luna: 부를 수 없다 (model_unavailable)'])


async def test_a_failure_shows_only_the_reason():
    code, lines = await try_once(router_with(LUNA, answer(status=401)), 'gpt-6-luna', PARAMS, lambda piece: None)

    # 응답의 본문과 키는 찍지 않는다
    assert (code, lines) == (1, ['gpt-6-luna: 부르다 실패했다 (status_401)'])
    assert all(KEY not in line for line in lines)


def test_the_command_line_makes_the_params():
    params = params_of(build_parser().parse_args(['gpt-6-luna', '--reasoning', 'low', '--max-tokens', '400']))

    assert (params.max_tokens, params.reasoning) == (400, Reasoning.LOW)
    # 적지 않으면 생각을 끄고 짧게 쓴다
    assert params_of(build_parser().parse_args(['gpt-6-luna'])) == PARAMS


async def test_the_cost_of_the_call_is_shown_with_the_price_of_the_day():
    priced = replace(LUNA, cost=UnitCost(cost_id=7, input_per_mtok=Decimal('0.1'), output_per_mtok=Decimal('0.5')))

    _, lines = await try_once(router_with(priced, answer()), 'gpt-6-luna', PARAMS, lambda piece: None)

    # 60 x 0.1 + 9 x 0.5 = 10.5 / 1,000,000
    assert lines[3] == '원가: $0.00001050'


async def test_a_model_outside_the_catalog_has_no_cost():
    _, lines = await try_once(router_with(LUNA, answer()), 'gemma4:26b', PARAMS, lambda piece: None)

    assert lines[3] == '원가: 모델 목록에 없는 모델이라 세지 않는다'


async def test_the_characters_sent_and_the_tokens_per_character_are_shown():
    code, lines = await try_once(router_with(LUNA, answer()), 'gpt-6-luna', PARAMS, lambda piece: None)

    # 서술의 입력 예산은 글자 수로 어림한다. 이 줄로 모델마다 글자당 토큰 수를 잰다
    chars = chars_of(MESSAGES)
    assert code == 0
    assert lines[5] == f'보낸 글자: {chars}자, 글자당 입력 토큰 {60 / chars:.2f}'


async def test_a_long_text_is_sent_after_the_system_line(tmp_path):
    path = tmp_path / 'long.txt'
    path.write_text('고속도로가 끝없이 이어진다. ' * 100, encoding='utf-8')

    messages = messages_of(read_text(path))
    code, lines = await try_once(router_with(LUNA, answer()), 'gpt-6-luna', PARAMS, lambda piece: None, messages)

    # 짧은 예시는 역할의 머리 같은 고정 토큰이 커서 비율이 부풀어 보인다. 긴 글로 잰다
    assert messages == [MESSAGES[0], ChatMessage(Role.USER, path.read_text(encoding='utf-8'))]
    assert lines[5].startswith(f'보낸 글자: {chars_of(messages)}자, ')
    assert build_parser().parse_args(['gpt-6-luna', '--text-file', str(path)]).text_file == path


def test_without_a_text_file_the_example_scene_is_sent():
    assert messages_of(read_text(None)) == MESSAGES
