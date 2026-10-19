# game-server/tests/test_gemini.py

"""
Gemini 를 부르는 provider(app/ai/gemini.py)와 흘려 받는 답을 읽는 것(app/ai/gemini_stream.py)을 검증한다.

실제 API 를 부르지 않는다. httpx 의 가짜 전송이 Google 인 척 답한다.
응답의 모양은 Google 의 문서(generateContent, 2026-10)를 따랐다.

넷을 본다.
  - 보내는 것: 주소(키는 주소에 싣지 않는다), 머리, 시스템 지시를 따로, 역할 이름, 저장하지 않음, 온도는 받는 모델에만.
  - 생각: 모델의 방식(level_minimal, level_low, budget, budget_min)마다 끄고 켜는 칸, 출력 상한에 더하는 생각의 몫.
  - 받는 것: 글 조각, 생각은 읽지 않음, 토큰 수를 OpenAI 의 뜻으로, 길이 상한, 막힌 요청, 끝까지 받지 못함.
  - 실패: 상태 코드와 대기 시간, 도중의 오류, 이상한 모양. 키와 본문은 싣지 않는다.
"""

import json

import httpx
import pytest
from pydantic import SecretStr

from app.ai.catalog_contract import ReasoningStyle
from app.ai.gemini import GeminiProvider, build_body, stream_url
from app.ai.openai_compat import THINKING_TOKENS
from app.ai.provider import ChatMessage, GenerationParams, ProviderError, Reasoning, Role

BASE_URL = 'https://generativelanguage.googleapis.com'
MODEL = 'gemini-4-argon'
KEY = 'g-test-key'
MESSAGES = [
    ChatMessage(Role.SYSTEM, '너는 GM 이다.'),
    ChatMessage(Role.USER, '엘프 폭주족이 달린다.'),
    ChatMessage(Role.ASSISTANT, '사이렌이 울린다.'),
    ChatMessage(Role.USER, '더 빨리 달린다.'),
]
PARAMS = GenerationParams(max_tokens=800, temperature=0.8)
SECRET = '악역영애는 사실 경찰의 끄나풀이다.'


def chunk(*parts: dict, finish: str | None = None, usage: dict | None = None, **extra) -> str:
    """SSE 의 응답 조각 하나."""
    candidate: dict = {'content': {'role': 'model', 'parts': list(parts)}, 'index': 0}
    if finish:
        candidate['finishReason'] = finish
    response: dict = {'candidates': [candidate], 'modelVersion': MODEL, **extra}
    if usage:
        response['usageMetadata'] = usage
    return f'data: {json.dumps(response, ensure_ascii=False)}\r\n\r\n'


def answer(*pieces: str, finish: str = 'STOP', usage: dict | None = None) -> str:
    """생각 조각 하나와 글 조각들이 오는 답 전부. 마지막 조각에 멈춘 이유와 토큰 수가 온다."""
    usage = usage or {'promptTokenCount': 25, 'candidatesTokenCount': 15, 'totalTokenCount': 40}
    body = [chunk({'text': SECRET, 'thought': True})]
    body += [chunk({'text': piece}) for piece in pieces[:-1]]
    body.append(chunk({'text': pieces[-1]}, finish=finish, usage=usage))
    return ''.join(body)


class Recorder:
    """가짜 전송이 받은 요청을 적어 두고, 정해 둔 답을 돌려준다."""

    def __init__(self, body: str, status: int = 200, headers: dict | None = None):
        self.answer = body
        self.status = status
        self.headers = headers or {}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, text=self.answer, headers=self.headers)

    def body(self) -> dict:
        (request,) = self.requests
        return json.loads(request.content)


def make_provider(recorder: Recorder, **overrides) -> GeminiProvider:
    values = {
        'client': httpx.AsyncClient(transport=httpx.MockTransport(recorder)),
        'base_url': BASE_URL,
        'model': MODEL,
        'api_key': SecretStr(KEY),
        'reasoning_style': ReasoningStyle.LEVEL_LOW,
    }
    values.update(overrides)
    return GeminiProvider(**values)


def config_for(style: ReasoningStyle, reasoning: Reasoning = Reasoning.NONE, temperature: bool = False) -> dict:
    """그 방식과 깊이로 만든 생성 설정."""
    params = GenerationParams(max_tokens=800, temperature=0.8, reasoning=reasoning)
    return build_body(MESSAGES, params, style, temperature)['generationConfig']


# --- 보내는 것 ---


@pytest.mark.parametrize('base_url', [BASE_URL, f'{BASE_URL}/'])
def test_the_address_streams_with_sse(base_url: str):
    assert stream_url(base_url, MODEL) == f'{BASE_URL}/v1beta/models/{MODEL}:streamGenerateContent?alt=sse'


async def test_the_key_goes_in_a_header_not_the_address():
    recorder = Recorder(answer('엔진 소리.'))

    await make_provider(recorder).complete(MESSAGES, PARAMS)

    (request,) = recorder.requests
    # 주소는 로그에 남을 수 있다. 키는 머리에만 싣는다
    assert request.headers['x-goog-api-key'] == KEY
    assert KEY not in str(request.url)
    assert str(request.url) == f'{BASE_URL}/v1beta/models/{MODEL}:streamGenerateContent?alt=sse'


def test_the_body_has_its_own_system_field_and_gemini_roles():
    body = build_body(MESSAGES, PARAMS, ReasoningStyle.LEVEL_LOW, False)

    assert body['systemInstruction'] == {'parts': [{'text': '너는 GM 이다.'}]}
    # 어시스턴트는 model 이다
    assert body['contents'] == [
        {'role': 'user', 'parts': [{'text': '엘프 폭주족이 달린다.'}]},
        {'role': 'model', 'parts': [{'text': '사이렌이 울린다.'}]},
        {'role': 'user', 'parts': [{'text': '더 빨리 달린다.'}]},
    ]
    # Google 쪽에 저장하지 말라고 한다
    assert body['store'] is False


def test_without_system_instructions_there_is_no_system_field():
    body = build_body([ChatMessage(Role.USER, '달린다.')], PARAMS, ReasoningStyle.LEVEL_LOW, False)

    assert 'systemInstruction' not in body


def test_the_temperature_goes_only_to_models_that_take_it():
    assert 'temperature' not in config_for(ReasoningStyle.LEVEL_LOW, temperature=False)
    assert config_for(ReasoningStyle.BUDGET, temperature=True)['temperature'] == 0.8


# --- 생각 ---


@pytest.mark.parametrize(
    ('style', 'thinking'),
    [
        (ReasoningStyle.LEVEL_MINIMAL, {'thinkingLevel': 'minimal'}),
        (ReasoningStyle.LEVEL_LOW, {'thinkingLevel': 'low'}),
        (ReasoningStyle.BUDGET_MIN, {'thinkingBudget': 128}),
    ],
)
def test_a_model_that_cannot_stop_thinking_thinks_as_little_as_it_can(style: ReasoningStyle, thinking: dict):
    config = config_for(style)

    assert config['thinkingConfig'] == thinking
    # 생각이 장면의 몫을 먹지 않게 상한에 생각의 몫을 더한다
    assert config['maxOutputTokens'] == 800 + THINKING_TOKENS[Reasoning.LOW]


def test_a_budget_model_turns_thinking_off_with_zero():
    config = config_for(ReasoningStyle.BUDGET)

    assert config['thinkingConfig'] == {'thinkingBudget': 0}
    assert config['maxOutputTokens'] == 800


@pytest.mark.parametrize('style', [ReasoningStyle.LEVEL_MINIMAL, ReasoningStyle.LEVEL_LOW])
def test_thinking_on_for_a_level_model_is_the_level(style: ReasoningStyle):
    config = config_for(style, Reasoning.HIGH)

    assert config['thinkingConfig'] == {'thinkingLevel': 'high'}
    assert config['maxOutputTokens'] == 800 + THINKING_TOKENS[Reasoning.HIGH]


@pytest.mark.parametrize('style', [ReasoningStyle.BUDGET, ReasoningStyle.BUDGET_MIN])
def test_thinking_on_for_a_budget_model_is_a_token_count(style: ReasoningStyle):
    config = config_for(style, Reasoning.MEDIUM)

    assert config['thinkingConfig'] == {'thinkingBudget': THINKING_TOKENS[Reasoning.MEDIUM]}
    assert config['maxOutputTokens'] == 800 + THINKING_TOKENS[Reasoning.MEDIUM]


def test_a_claude_style_is_refused():
    with pytest.raises(ValueError):
        config_for(ReasoningStyle.ADAPTIVE)


# --- 받는 것 ---


async def test_the_text_pieces_become_a_completion_and_the_thinking_is_dropped():
    pieces: list[str] = []

    completion = await make_provider(Recorder(answer('엔진 소리가 ', '골목을 메운다.'))).complete(
        MESSAGES, PARAMS, pieces.append
    )

    assert pieces == ['엔진 소리가 ', '골목을 메운다.']
    assert completion.text == '엔진 소리가 골목을 메운다.'
    assert SECRET not in completion.text
    assert (completion.model, completion.finish_reason, completion.truncated) == (MODEL, 'STOP', False)


async def test_the_token_counts_are_put_in_the_openai_sense():
    usage = {
        'promptTokenCount': 12_000,
        'cachedContentTokenCount': 8_000,
        'candidatesTokenCount': 1_000,
        'thoughtsTokenCount': 600,
        'totalTokenCount': 13_600,
    }

    completion = await make_provider(Recorder(answer('장면.', usage=usage))).complete(MESSAGES, PARAMS)

    # 입력에는 캐시가 들어 있다. 출력에는 생각이 빠져 있어 더한다(생각도 출력으로 값이 매겨진다)
    assert (completion.input_tokens, completion.cached_input_tokens) == (12_000, 8_000)
    assert (completion.output_tokens, completion.reasoning_tokens) == (1_600, 600)
    assert completion.cache_write_tokens is None


async def test_an_answer_cut_by_the_length_limit_is_truncated():
    completion = await make_provider(Recorder(answer('엔진 소', finish='MAX_TOKENS'))).complete(MESSAGES, PARAMS)

    assert completion.truncated


async def test_a_blocked_request_ends_without_text():
    body = f'data: {json.dumps({"promptFeedback": {"blockReason": "SAFETY"}})}\r\n\r\n'

    completion = await make_provider(Recorder(body)).complete(MESSAGES, PARAMS)

    # 서술자가 빈 글로 거절한다(empty). 막힌 까닭은 멈춘 이유로 남는다
    assert (completion.text, completion.finish_reason) == ('', 'SAFETY')


async def test_an_answer_without_a_finish_is_interrupted():
    with pytest.raises(ProviderError, match='interrupted'):
        await make_provider(Recorder(chunk({'text': '엔진'}))).complete(MESSAGES, PARAMS)


# --- 실패 ---


async def test_an_error_status_carries_the_told_wait():
    recorder = Recorder('{"error": {"status": "RESOURCE_EXHAUSTED"}}', status=429, headers={'retry-after': '9'})

    with pytest.raises(ProviderError) as caught:
        await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert (str(caught.value), caught.value.retry_after) == ('status_429', 9.0)


async def test_an_error_in_the_middle_of_the_stream_is_a_stream_error():
    body = chunk({'text': '엔진'}) + f'data: {json.dumps({"error": {"message": SECRET}})}\r\n\r\n'

    with pytest.raises(ProviderError) as caught:
        await make_provider(Recorder(body)).complete(MESSAGES, PARAMS)

    assert str(caught.value) == 'stream_error'


@pytest.mark.parametrize(
    'data', ['not json', '[]', '{"candidates": "x"}', '{"candidates": [{"content": {"parts": [{"text": 3}]}}]}']
)
async def test_a_strange_response_is_malformed(data: str):
    with pytest.raises(ProviderError, match='malformed'):
        await make_provider(Recorder(f'data: {data}\r\n\r\n')).complete(MESSAGES, PARAMS)


async def test_the_key_and_the_body_are_not_in_an_error():
    recorder = Recorder(f'{{"error": "{KEY} {SECRET}"}}', status=403)

    with pytest.raises(ProviderError) as caught:
        await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert str(caught.value) == 'status_403'
    assert KEY not in repr(caught.value)


def test_the_key_is_not_in_the_repr_of_the_provider():
    assert KEY not in repr(make_provider(Recorder('')))
