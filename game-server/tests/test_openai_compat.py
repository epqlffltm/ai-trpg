# game-server/tests/test_openai_compat.py

"""
OpenAI 와 같은 모양의 주소를 부르는 provider(app/ai/openai_compat.py)를 검증한다.

실제 모델을 부르지 않는다. httpx 의 가짜 전송(MockTransport)이 Ollama 인 척 답한다.
답의 모양은 Ollama 0.40 에서 직접 확인한 것을 따른다(추론 글은 reasoning 칸, 끊기면 finish_reason 이 length).
"""

import json
from collections.abc import Callable

import httpx
import pytest

from app.ai import openai_compat
from app.ai.openai_compat import (
    OpenAICompatProvider,
    build_body,
    chat_url,
    drop_thinking,
    read_completion,
    token_limit,
)
from app.ai.provider import ChatMessage, GenerationParams, ProviderError, Reasoning, Role

BASE_URL = 'http://127.0.0.1:11434/v1'
MODEL = 'gemma4:26b'
MESSAGES = [ChatMessage(Role.SYSTEM, '너는 GM 이다.'), ChatMessage(Role.USER, '엘프 폭주족이 달린다.')]
PARAMS = GenerationParams(max_tokens=800, temperature=0.8)
SCENE = '엔진 소리가 골목을 메운다.'
# 응답 본문에 되돌아온 프롬프트. 오류 메시지에 실리면 안 된다
SECRET = '악역영애는 사실 경찰의 끄나풀이다.'


def make_answer(content: str | None = SCENE, finish: str = 'stop', **extra) -> dict:
    """Ollama 가 돌려주는 모양의 답."""
    answer = {
        'model': MODEL,
        'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content}, 'finish_reason': finish}],
        'usage': {'prompt_tokens': 21, 'completion_tokens': 53, 'total_tokens': 74},
    }
    answer.update(extra)
    return answer


class Recorder:
    """가짜 전송이 받은 요청을 적어 두고, 정해 둔 답을 돌려준다."""

    def __init__(self, respond: Callable[[httpx.Request], httpx.Response]):
        self.respond = respond
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.respond(request)

    def body(self) -> dict:
        (request,) = self.requests
        return json.loads(request.content)


def answering(answer: dict, status: int = 200) -> Recorder:
    return Recorder(lambda request: httpx.Response(status, json=answer))


def make_provider(recorder: Callable, **overrides) -> OpenAICompatProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    values = {'client': client, 'base_url': BASE_URL, 'model': MODEL}
    values.update(overrides)
    return OpenAICompatProvider(**values)


# --- 보내는 것 ---


@pytest.mark.parametrize('base_url', [BASE_URL, f'{BASE_URL}/'])
def test_the_address_ends_with_chat_completions(base_url: str):
    assert chat_url(base_url) == f'{BASE_URL}/chat/completions'


async def test_the_request_goes_to_the_chat_address():
    recorder = answering(make_answer())

    await make_provider(recorder).complete(MESSAGES, PARAMS)

    (request,) = recorder.requests
    assert request.method == 'POST'
    assert str(request.url) == f'{BASE_URL}/chat/completions'


async def test_the_body_carries_the_model_the_messages_and_the_settings():
    recorder = answering(make_answer())

    await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert recorder.body() == {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': '너는 GM 이다.'},
            {'role': 'user', 'content': '엘프 폭주족이 달린다.'},
        ],
        'max_tokens': 800,
        'temperature': 0.8,
        'stream': False,
        # 끌 때도 보낸다. 보내지 않으면 추론하는 모델은 생각부터 한다
        'reasoning_effort': 'none',
    }


def test_reasoning_is_off_by_default():
    assert PARAMS.reasoning == Reasoning.NONE
    assert token_limit(PARAMS, supports_reasoning=True) == 800


@pytest.mark.parametrize('reasoning', [Reasoning.LOW, Reasoning.MEDIUM, Reasoning.HIGH])
def test_reasoning_gets_its_own_tokens(reasoning: Reasoning):
    params = GenerationParams(max_tokens=800, temperature=0.8, reasoning=reasoning)

    body = build_body(MODEL, MESSAGES, params, supports_reasoning=True)

    # 생각이 답의 몫까지 먹으면 답이 비어 온다. 생각의 몫을 따로 더한다
    assert body['max_tokens'] == 800 + openai_compat.THINKING_TOKENS[reasoning]
    assert body['reasoning_effort'] == reasoning.value


def test_a_model_without_reasoning_gets_no_reasoning_field():
    params = GenerationParams(max_tokens=800, temperature=0.8, reasoning=Reasoning.HIGH)

    body = build_body(MODEL, MESSAGES, params, supports_reasoning=False)

    assert 'reasoning_effort' not in body
    assert body['max_tokens'] == 800


async def test_the_timeout_is_passed_on():
    seen: list[dict] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions['timeout'])
        return httpx.Response(200, json=make_answer())

    await make_provider(respond, timeout=7.5).complete(MESSAGES, PARAMS)

    (timeout,) = seen
    assert timeout['read'] == 7.5


# --- 받는 것 ---


async def test_the_answer_becomes_a_completion():
    completion = await make_provider(answering(make_answer())).complete(MESSAGES, PARAMS)

    assert completion.text == SCENE
    assert completion.model == MODEL
    assert completion.input_tokens == 21
    assert completion.output_tokens == 53
    assert completion.finish_reason == 'stop'
    assert completion.truncated is False


async def test_an_answer_cut_by_the_length_limit_is_marked_truncated():
    completion = await make_provider(answering(make_answer(finish='length'))).complete(MESSAGES, PARAMS)

    assert completion.truncated is True


async def test_the_thinking_in_its_own_field_is_not_read():
    # Ollama 는 생각 글을 reasoning 칸에 담는다. 생각만 하다 끊기면 content 가 비어 온다
    answer = make_answer(content='', finish='length')
    answer['choices'][0]['message']['reasoning'] = f'범인은... {SECRET}'

    completion = await make_provider(answering(answer)).complete(MESSAGES, PARAMS)

    assert completion.text == ''
    assert SECRET not in completion.text
    assert completion.truncated is True


async def test_thinking_mixed_into_the_answer_does_not_reach_the_text():
    answer = make_answer(content=f'<think>{SECRET}</think>{SCENE}')

    completion = await make_provider(answering(answer)).complete(MESSAGES, PARAMS)

    # 생각 글에는 GM 메모를 따져 본 내용이 들어 있을 수 있다. 장면이 되면 플레이어에게 보인다
    assert completion.text == SCENE


async def test_an_answer_with_no_content_is_an_empty_text():
    completion = await make_provider(answering(make_answer(content=None))).complete(MESSAGES, PARAMS)

    assert completion.text == ''


async def test_missing_usage_leaves_the_counts_empty():
    answer = make_answer()
    del answer['usage']

    completion = await make_provider(answering(answer)).complete(MESSAGES, PARAMS)

    assert completion.input_tokens is None
    assert completion.output_tokens is None


async def test_the_model_name_falls_back_to_the_one_asked_for():
    answer = make_answer()
    del answer['model']

    completion = await make_provider(answering(answer)).complete(MESSAGES, PARAMS)

    assert completion.model == MODEL


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        (f'<think>범인을 따져 보자.</think>{SCENE}', SCENE),
        (f'<think>\n여러 줄의\n생각\n</think>\n{SCENE}', f'\n{SCENE}'),
        (f'{SCENE}<think>뒤에 붙은 생각</think>', SCENE),
        ('<think>끝나지 않은 생각', ''),
        (SCENE, SCENE),
    ],
)
def test_thinking_mixed_into_the_content_is_dropped(text: str, expected: str):
    assert drop_thinking(text) == expected


# --- 실패 ---


@pytest.mark.parametrize('status', [400, 404, 500, 503])
async def test_an_error_status_is_a_provider_error(status: int):
    recorder = answering({'error': {'message': SECRET}}, status=status)

    with pytest.raises(ProviderError) as caught:
        await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert str(caught.value) == f'status_{status}'


async def test_the_body_of_an_error_is_not_in_the_message():
    recorder = Recorder(lambda request: httpx.Response(500, text=f'echo: {SECRET}'))

    with pytest.raises(ProviderError) as caught:
        await make_provider(recorder).complete(MESSAGES, PARAMS)

    # 본문에는 보낸 프롬프트(GM 메모 포함)가 되돌아와 있을 수 있다. 로그에 남으면 안 된다
    assert SECRET not in str(caught.value)


async def test_a_refused_connection_is_a_provider_error():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('연결 거부', request=request)

    with pytest.raises(ProviderError) as caught:
        await make_provider(refuse).complete(MESSAGES, PARAMS)

    assert str(caught.value) == 'unreachable'


async def test_a_timeout_is_a_provider_error():
    def hang(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout('시간 초과', request=request)

    with pytest.raises(ProviderError) as caught:
        await make_provider(hang).complete(MESSAGES, PARAMS)

    assert str(caught.value) == 'timeout'


async def test_an_answer_that_is_not_json_is_a_provider_error():
    recorder = Recorder(lambda request: httpx.Response(200, text='<html>proxy error</html>'))

    with pytest.raises(ProviderError) as caught:
        await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert str(caught.value) == 'not_json'


@pytest.mark.parametrize(
    'data',
    [
        {},
        {'choices': []},
        {'choices': [{}]},
        {'choices': [{'message': 'text'}]},
        {'choices': [{'message': {'content': 3}}]},
        [],
        'text',
    ],
)
def test_an_answer_of_the_wrong_shape_is_a_provider_error(data):
    with pytest.raises(ProviderError) as caught:
        read_completion(data, MODEL)

    assert str(caught.value) == 'malformed'
