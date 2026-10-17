# game-server/tests/test_anthropic.py

"""
Claude 를 부르는 provider(app/ai/anthropic.py)와 흘려 받는 답을 읽는 것(app/ai/anthropic_stream.py)을 검증한다.

실제 API 를 부르지 않는다. httpx 의 가짜 전송이 Anthropic 인 척 답한다.
이벤트의 모양은 Anthropic 의 문서(2026-10)를 따랐다.

넷을 본다.
  - 보내는 것: 주소, 머리(키, API 의 판), 시스템 지시를 따로, 온도는 받는 모델에만.
  - 생각: 모델의 방식(adaptive, always, between_tools, budget)마다 끄고 켜는 칸, 출력 상한에 더하는 생각의 몫.
  - 받는 것: 글 조각, 생각은 읽지 않음, 토큰 수를 OpenAI 의 뜻으로, 길이 상한에 걸림, 끝까지 받지 못함.
  - 실패: 상태 코드와 대기 시간, 과부하(529), 도중의 오류, 이상한 모양. 키와 본문은 싣지 않는다.
"""

import json

import httpx
import pytest
from pydantic import SecretStr

from app.ai.anthropic import (
    ANTHROPIC_VERSION,
    AnthropicProvider,
    build_body,
    messages_url,
)
from app.ai.openai_compat import THINKING_TOKENS
from app.ai.provider import ChatMessage, GenerationParams, ProviderError, Reasoning, Role
from app.ai.thinking import thinking_budget
from app.catalog.models import ReasoningStyle

BASE_URL = 'https://api.anthropic.com'
MODEL = 'claude-opus-5-5-20260901'
KEY = 'sk-ant-test'
MESSAGES = [
    ChatMessage(Role.SYSTEM, '너는 GM 이다.'),
    ChatMessage(Role.SYSTEM, '반말로 쓴다.'),
    ChatMessage(Role.USER, '엘프 폭주족이 달린다.'),
]
PARAMS = GenerationParams(max_tokens=800, temperature=0.8)
SECRET = '악역영애는 사실 경찰의 끄나풀이다.'


def event(kind: str, **fields) -> str:
    """SSE 의 이벤트 하나. event 줄과 data 줄이다."""
    return f'event: {kind}\ndata: {json.dumps({"type": kind, **fields}, ensure_ascii=False)}\n\n'


def start(usage: dict | None = None) -> str:
    """message_start. 답한 모델과 입력의 토큰 수."""
    usage = usage or {'input_tokens': 25, 'output_tokens': 1}
    message = {'id': 'msg_1', 'type': 'message', 'role': 'assistant', 'content': [], 'model': MODEL, 'usage': usage}
    return event('message_start', message=message)


def text(piece: str, index: int = 1) -> str:
    """글 조각."""
    return event('content_block_delta', index=index, delta={'type': 'text_delta', 'text': piece})


def finish(stop_reason: str = 'end_turn', usage: dict | None = None) -> str:
    """message_delta. 멈춘 이유와 누적 토큰 수."""
    return event(
        'message_delta', delta={'stop_reason': stop_reason, 'stop_sequence': None}, usage=usage or {'output_tokens': 15}
    )


def answer(*pieces: str, stop_reason: str = 'end_turn') -> str:
    """생각 블록 하나와 글 조각들이 오는 답 전부."""
    return ''.join(
        [
            start(),
            event('content_block_start', index=0, content_block={'type': 'thinking', 'thinking': ''}),
            event('content_block_delta', index=0, delta={'type': 'thinking_delta', 'thinking': SECRET}),
            event('content_block_delta', index=0, delta={'type': 'signature_delta', 'signature': 'Eq…'}),
            event('content_block_stop', index=0),
            event('content_block_start', index=1, content_block={'type': 'text', 'text': ''}),
            event('ping'),
            *(text(piece) for piece in pieces),
            event('content_block_stop', index=1),
            finish(stop_reason),
            event('message_stop'),
        ]
    )


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


def make_provider(recorder: Recorder, **overrides) -> AnthropicProvider:
    values = {
        'client': httpx.AsyncClient(transport=httpx.MockTransport(recorder)),
        'base_url': BASE_URL,
        'model': MODEL,
        'api_key': SecretStr(KEY),
        'reasoning_style': ReasoningStyle.ADAPTIVE,
    }
    values.update(overrides)
    return AnthropicProvider(**values)


def body_for(style: ReasoningStyle, reasoning: Reasoning = Reasoning.NONE, temperature: bool = False) -> dict:
    """그 방식과 깊이로 만든 본문."""
    params = GenerationParams(max_tokens=800, temperature=0.8, reasoning=reasoning)
    return build_body(MODEL, MESSAGES, params, style, temperature)


# --- 보내는 것 ---


@pytest.mark.parametrize('base_url', [BASE_URL, f'{BASE_URL}/'])
def test_the_address_ends_with_v1_messages(base_url: str):
    assert messages_url(base_url) == f'{BASE_URL}/v1/messages'


async def test_the_request_carries_the_key_and_the_api_version():
    recorder = Recorder(answer('엔진 소리.'))

    await make_provider(recorder).complete(MESSAGES, PARAMS)

    (request,) = recorder.requests
    assert str(request.url) == f'{BASE_URL}/v1/messages'
    assert request.headers['Authorization'] == f'Bearer {KEY}'
    assert request.headers['anthropic-version'] == ANTHROPIC_VERSION


def test_the_system_instructions_go_in_their_own_field():
    body = body_for(ReasoningStyle.ADAPTIVE)

    # Claude 는 시스템 지시를 메시지 목록에 받지 않는다
    assert body['system'] == '너는 GM 이다.\n\n반말로 쓴다.'
    assert body['messages'] == [{'role': 'user', 'content': '엘프 폭주족이 달린다.'}]
    assert (body['model'], body['stream']) == (MODEL, True)


def test_without_system_instructions_there_is_no_system_field():
    params = GenerationParams(max_tokens=800, temperature=0.8)

    body = build_body(MODEL, [ChatMessage(Role.USER, '달린다.')], params, ReasoningStyle.ADAPTIVE, False)

    assert 'system' not in body


def test_the_temperature_goes_only_to_models_that_take_it():
    # 5 세대와 Opus 4.7·4.8 은 기본값이 아닌 온도에 400 을 낸다
    assert 'temperature' not in body_for(ReasoningStyle.ADAPTIVE, temperature=False)
    assert body_for(ReasoningStyle.ADAPTIVE, temperature=True)['temperature'] == 0.8


# --- 생각 ---


@pytest.mark.parametrize(
    ('style', 'thinking'),
    [
        (ReasoningStyle.ADAPTIVE, {'type': 'disabled'}),
        (ReasoningStyle.BETWEEN_TOOLS, {'type': 'between_tools'}),
        (ReasoningStyle.BUDGET, {'type': 'disabled'}),
    ],
)
def test_thinking_is_turned_off_the_way_the_model_takes(style: ReasoningStyle, thinking: dict):
    body = body_for(style)

    assert body['thinking'] == thinking
    assert 'output_config' not in body
    # 생각하지 않으므로 출력 상한은 장면의 몫뿐이다
    assert body['max_tokens'] == 800


def test_a_model_that_always_thinks_thinks_as_little_as_it_can():
    body = body_for(ReasoningStyle.ALWAYS)

    # 끌 수 없다. 가장 낮은 깊이로 생각하게 하고, 생각이 장면의 몫을 먹지 않게 상한에 생각의 몫을 더한다
    assert body['thinking'] == {'type': 'adaptive', 'display': 'omitted'}
    assert body['output_config'] == {'effort': 'low'}
    assert body['max_tokens'] == 800 + THINKING_TOKENS[Reasoning.LOW]


@pytest.mark.parametrize('style', [ReasoningStyle.ADAPTIVE, ReasoningStyle.ALWAYS, ReasoningStyle.BETWEEN_TOOLS])
def test_thinking_on_is_adaptive_with_an_effort(style: ReasoningStyle):
    body = body_for(style, Reasoning.MEDIUM)

    # 생각한 글은 돌려받지 않는다(받아도 읽지 않는다)
    assert body['thinking'] == {'type': 'adaptive', 'display': 'omitted'}
    assert body['output_config'] == {'effort': 'medium'}
    assert body['max_tokens'] == 800 + THINKING_TOKENS[Reasoning.MEDIUM]


def test_thinking_on_for_the_older_models_is_a_token_budget():
    body = body_for(ReasoningStyle.BUDGET, Reasoning.HIGH)

    # 4.5 세대는 adaptive 에 400 을 낸다. 생각의 토큰 상한을 준다. 출력 상한은 그보다 커야 한다
    assert body['thinking'] == {'type': 'enabled', 'budget_tokens': THINKING_TOKENS[Reasoning.HIGH]}
    assert 'output_config' not in body
    assert body['max_tokens'] == 800 + THINKING_TOKENS[Reasoning.HIGH]


@pytest.mark.parametrize(
    ('style', 'reasoning', 'budget'),
    [
        (ReasoningStyle.ADAPTIVE, Reasoning.NONE, 0),
        (ReasoningStyle.BUDGET, Reasoning.NONE, 0),
        (ReasoningStyle.BETWEEN_TOOLS, Reasoning.NONE, 0),
        (ReasoningStyle.ALWAYS, Reasoning.NONE, THINKING_TOKENS[Reasoning.LOW]),
        (ReasoningStyle.ALWAYS, Reasoning.HIGH, THINKING_TOKENS[Reasoning.HIGH]),
        (ReasoningStyle.ADAPTIVE, Reasoning.LOW, THINKING_TOKENS[Reasoning.LOW]),
    ],
)
def test_the_thinking_budget(style: ReasoningStyle, reasoning: Reasoning, budget: int):
    assert thinking_budget(style, reasoning) == budget


# --- 받는 것 ---


async def test_the_text_pieces_become_a_completion_and_the_thinking_is_dropped():
    pieces: list[str] = []

    completion = await make_provider(Recorder(answer('엔진 소리가 ', '골목을 메운다.'))).complete(
        MESSAGES, PARAMS, pieces.append
    )

    # 생각 블록은 넘기지도 담지도 않는다
    assert pieces == ['엔진 소리가 ', '골목을 메운다.']
    assert completion.text == '엔진 소리가 골목을 메운다.'
    assert SECRET not in completion.text
    assert (completion.model, completion.finish_reason, completion.truncated) == (MODEL, 'end_turn', False)


async def test_the_token_counts_are_put_in_the_openai_sense():
    body = ''.join(
        [
            start({'input_tokens': 2_000, 'cache_creation_input_tokens': 3_000, 'cache_read_input_tokens': 7_000}),
            text('장면.'),
            finish(usage={'output_tokens': 1_500}),
            event('message_stop'),
        ]
    )

    completion = await make_provider(Recorder(body)).complete(MESSAGES, PARAMS)

    # Claude 의 input_tokens 에는 캐시가 빠져 있다. 셋을 더한 것이 보낸 입력 전부다
    assert (completion.input_tokens, completion.cached_input_tokens, completion.cache_write_tokens) == (
        12_000,
        7_000,
        3_000,
    )
    # 출력에는 생각이 들어 있다. 생각만 따로 세어 주지 않는다
    assert (completion.output_tokens, completion.reasoning_tokens) == (1_500, None)


async def test_the_cumulative_counts_of_the_last_delta_win():
    body = ''.join(
        [
            start({'input_tokens': 25, 'output_tokens': 1}),
            text('장면.'),
            finish(usage={'input_tokens': 30, 'output_tokens': 40}),
            event('message_stop'),
        ]
    )

    completion = await make_provider(Recorder(body)).complete(MESSAGES, PARAMS)

    assert (completion.input_tokens, completion.output_tokens) == (30, 40)


async def test_an_answer_cut_by_the_length_limit_is_truncated():
    completion = await make_provider(Recorder(answer('엔진 소', stop_reason='max_tokens'))).complete(MESSAGES, PARAMS)

    assert completion.truncated


async def test_an_answer_that_ends_too_early_is_interrupted():
    with pytest.raises(ProviderError, match='interrupted'):
        await make_provider(Recorder(start() + text('엔진'))).complete(MESSAGES, PARAMS)


async def test_unknown_events_are_passed_over():
    body = start() + event('brand_new_event', note='?') + text('장면.') + finish() + event('message_stop')

    assert (await make_provider(Recorder(body)).complete(MESSAGES, PARAMS)).text == '장면.'


# --- 실패 ---


async def test_an_error_status_carries_the_told_wait():
    recorder = Recorder('{"type": "error"}', status=429, headers={'retry-after': '12'})

    with pytest.raises(ProviderError) as caught:
        await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert (str(caught.value), caught.value.retry_after) == ('status_429', 12.0)


async def test_an_overload_is_status_529():
    with pytest.raises(ProviderError, match='status_529'):
        await make_provider(Recorder('{"error": "overloaded"}', status=529)).complete(MESSAGES, PARAMS)


async def test_an_error_in_the_middle_of_the_stream_is_a_stream_error():
    body = start() + text('엔진') + event('error', error={'type': 'overloaded_error', 'message': SECRET})

    with pytest.raises(ProviderError) as caught:
        await make_provider(Recorder(body)).complete(MESSAGES, PARAMS)

    # 오류의 내용은 싣지 않는다
    assert str(caught.value) == 'stream_error'


@pytest.mark.parametrize('data', ['not json', '[]', '{"no_type": 1}'])
async def test_a_strange_event_is_malformed(data: str):
    with pytest.raises(ProviderError, match='malformed'):
        await make_provider(Recorder(start() + f'data: {data}\n\n')).complete(MESSAGES, PARAMS)


async def test_the_key_and_the_body_are_not_in_an_error():
    recorder = Recorder(f'{{"error": "{KEY} {SECRET}"}}', status=401)

    with pytest.raises(ProviderError) as caught:
        await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert str(caught.value) == 'status_401'
    assert KEY not in repr(caught.value)


def test_the_key_is_not_in_the_repr_of_the_provider():
    assert KEY not in repr(make_provider(Recorder('')))
