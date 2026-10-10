# game-server/tests/test_openai_compat.py

"""
OpenAI 와 같은 모양의 주소를 부르는 provider(app/ai/openai_compat.py)를 검증한다.

실제 모델을 부르지 않는다. httpx 의 가짜 전송(MockTransport)이 Ollama 인 척 답한다.
답은 흘려 보내는 모양(SSE)이다. 조각마다 delta.content, 멈춘 이유는 마지막 글 조각, 토큰 수는 맨 끝 조각에 온다.
추론 글은 reasoning 칸에 온다(Ollama 0.40 에서 직접 확인한 것).
줄을 읽는 일 자체는 tests/test_streaming.py 가 본다. 여기서는 HTTP 와 실패의 이름을 본다.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from app.ai import openai_compat
from app.ai.openai_compat import OpenAICompatProvider, build_body, chat_url, token_limit
from app.ai.provider import ChatMessage, GenerationParams, ProviderError, Reasoning, Role

BASE_URL = 'http://127.0.0.1:11434/v1'
MODEL = 'gemma4:26b'
MESSAGES = [ChatMessage(Role.SYSTEM, '너는 GM 이다.'), ChatMessage(Role.USER, '엘프 폭주족이 달린다.')]
PARAMS = GenerationParams(max_tokens=800, temperature=0.8)
SCENE = '엔진 소리가 골목을 메운다.'
# 응답 본문에 되돌아온 프롬프트. 오류 메시지에 실리면 안 된다
SECRET = '악역영애는 사실 경찰의 끄나풀이다.'
USAGE = {'prompt_tokens': 21, 'completion_tokens': 53, 'total_tokens': 74}


def piece(content: str | None = None, finish: str | None = None, **delta) -> dict:
    """Ollama 가 흘려 보내는 조각 하나."""
    if content is not None:
        delta['content'] = content
    return {'model': MODEL, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}


def usage_piece() -> dict:
    """맨 끝에 오는 토큰 수의 조각. choices 가 비어 있다."""
    return {'model': MODEL, 'choices': [], 'usage': USAGE}


def sse(*items: dict | str) -> str:
    """조각들을 SSE 의 글자로. 글자는 그대로(DONE 등), 사전은 JSON 으로 싣는다."""
    return ''.join(
        f'data: {item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)}\n\n' for item in items
    )


def make_stream(*contents: str, finish: str = 'stop') -> str:
    """글 조각들, 멈춘 이유, 토큰 수, [DONE] 이 차례로 오는 답."""
    return sse(*(piece(content) for content in contents), piece(finish=finish), usage_piece(), '[DONE]')


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


def streaming(text: str, status: int = 200) -> Recorder:
    """정해 둔 글자를 흘려 보내는 답으로 돌려준다."""
    headers = {'content-type': 'text/event-stream'}
    return Recorder(lambda request: httpx.Response(status, text=text, headers=headers))


class Broken(httpx.AsyncByteStream):
    """앞부분을 보내다가 연결이 끊기는(또는 멈춰 서는) 본문."""

    def __init__(self, sent: str, error: Exception | None = None, stall: float = 0.0):
        self.sent = sent
        self.error = error
        self.stall = stall

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self.sent.encode()
        if self.stall:
            await asyncio.sleep(self.stall)
        if self.error is not None:
            raise self.error


def breaking(stream: httpx.AsyncByteStream) -> Recorder:
    return Recorder(lambda request: httpx.Response(200, stream=stream))


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
    recorder = streaming(make_stream(SCENE))

    await make_provider(recorder).complete(MESSAGES, PARAMS)

    (request,) = recorder.requests
    assert request.method == 'POST'
    assert str(request.url) == f'{BASE_URL}/chat/completions'


async def test_the_body_carries_the_model_the_messages_and_the_settings():
    recorder = streaming(make_stream(SCENE))

    await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert recorder.body() == {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': '너는 GM 이다.'},
            {'role': 'user', 'content': '엘프 폭주족이 달린다.'},
        ],
        'max_tokens': 800,
        'temperature': 0.8,
        # 늘 흘려 받는다. 토큰 수는 따로 달라고 해야 온다
        'stream': True,
        'stream_options': {'include_usage': True},
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
        return httpx.Response(200, text=make_stream(SCENE))

    await make_provider(respond, timeout=7.5).complete(MESSAGES, PARAMS)

    (timeout,) = seen
    assert timeout['read'] == 7.5


# --- 받는 것 ---


async def test_the_pieces_become_a_completion():
    recorder = streaming(make_stream('엔진 소리가 ', '골목을 ', '메운다.'))

    completion = await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert completion.text == SCENE
    assert completion.model == MODEL
    assert completion.input_tokens == 21
    assert completion.output_tokens == 53
    assert completion.finish_reason == 'stop'
    assert completion.truncated is False


async def test_new_text_is_handed_on_as_it_arrives():
    received: list[str] = []
    recorder = streaming(make_stream('엔진 소리가 ', '골목을 ', '메운다.'))

    completion = await make_provider(recorder).complete(MESSAGES, PARAMS, received.append)

    assert received == ['엔진 소리가 ', '골목을 ', '메운다.']
    assert ''.join(received) == completion.text


async def test_handing_on_text_is_optional():
    completion = await make_provider(streaming(make_stream(SCENE))).complete(MESSAGES, PARAMS)

    assert completion.text == SCENE


async def test_an_answer_cut_by_the_length_limit_is_marked_truncated():
    recorder = streaming(make_stream(SCENE, finish='length'))

    completion = await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert completion.truncated is True


async def test_the_thinking_in_its_own_field_is_neither_read_nor_handed_on():
    # Ollama 는 생각 글을 reasoning 칸에 담는다. 생각만 하다 끊기면 content 가 비어 온다
    received: list[str] = []
    recorder = streaming(sse(piece(reasoning=f'범인은... {SECRET}'), piece(finish='length'), '[DONE]'))

    completion = await make_provider(recorder).complete(MESSAGES, PARAMS, received.append)

    assert completion.text == ''
    assert received == []
    assert completion.truncated is True


async def test_thinking_mixed_into_the_answer_is_neither_kept_nor_handed_on():
    received: list[str] = []
    recorder = streaming(make_stream('<thi', f'nk>{SECRET}</th', 'ink>', SCENE))

    completion = await make_provider(recorder).complete(MESSAGES, PARAMS, received.append)

    # 생각 글에는 GM 메모를 따져 본 내용이 들어 있을 수 있다. 미리 보기로라도 플레이어에게 가면 안 된다
    assert completion.text == SCENE
    assert ''.join(received) == SCENE


async def test_missing_usage_leaves_the_counts_empty():
    # include_usage 를 모르는 서버는 토큰 수를 보내지 않는다
    recorder = streaming(sse(piece(SCENE), piece(finish='stop'), '[DONE]'))

    completion = await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert completion.input_tokens is None
    assert completion.output_tokens is None


async def test_the_model_name_falls_back_to_the_one_asked_for():
    recorder = streaming(sse({'choices': [{'delta': {'content': SCENE}, 'finish_reason': 'stop'}]}, '[DONE]'))

    completion = await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert completion.model == MODEL


# --- 실패 ---


@pytest.mark.parametrize('status', [400, 404, 500, 503])
async def test_an_error_status_is_a_provider_error(status: int):
    recorder = Recorder(lambda request: httpx.Response(status, json={'error': {'message': SECRET}}))

    with pytest.raises(ProviderError) as caught:
        await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert str(caught.value) == f'status_{status}'


async def test_the_body_of_an_error_is_not_in_the_message():
    recorder = Recorder(lambda request: httpx.Response(500, text=f'echo: {SECRET}'))

    with pytest.raises(ProviderError) as caught:
        await make_provider(recorder).complete(MESSAGES, PARAMS)

    # 본문에는 보낸 프롬프트(GM 메모 포함)가 되돌아와 있을 수 있다. 로그에 남으면 안 된다
    assert SECRET not in str(caught.value)


async def test_an_error_piece_in_the_middle_is_a_provider_error():
    recorder = streaming(sse(piece('엔진 소리가 '), {'error': {'message': SECRET}}))

    with pytest.raises(ProviderError) as caught:
        await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert str(caught.value) == 'stream_error'
    assert SECRET not in str(caught.value)


async def test_a_refused_connection_is_a_provider_error():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('연결 거부', request=request)

    with pytest.raises(ProviderError) as caught:
        await make_provider(refuse).complete(MESSAGES, PARAMS)

    assert str(caught.value) == 'unreachable'


async def test_a_timeout_before_the_answer_is_a_provider_error():
    def hang(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout('시간 초과', request=request)

    with pytest.raises(ProviderError) as caught:
        await make_provider(hang).complete(MESSAGES, PARAMS)

    assert str(caught.value) == 'timeout'


async def test_a_connection_lost_while_reading_is_interrupted_not_unreachable():
    recorder = breaking(Broken(sse(piece('엔진 소리가 ')), httpx.ReadError('끊김')))

    with pytest.raises(ProviderError) as caught:
        await make_provider(recorder).complete(MESSAGES, PARAMS)

    # 서버가 꺼진 것(unreachable)과 한 번 끊긴 것은 다르다. 끊긴 것은 다른 모델로 넘어가 볼 만하다
    assert str(caught.value) == 'interrupted'


async def test_a_stall_while_reading_is_a_timeout():
    recorder = breaking(Broken(sse(piece('엔진 소리가 ')), httpx.ReadTimeout('조용함')))

    with pytest.raises(ProviderError) as caught:
        await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert str(caught.value) == 'timeout'


async def test_the_whole_call_has_a_time_limit_even_while_pieces_keep_coming():
    # 조각 사이의 간격(httpx 의 timeout)은 넘지 않지만 전체로는 넘는다
    recorder = breaking(Broken(sse(piece('엔진 소리가 ')), stall=0.5))

    with pytest.raises(ProviderError) as caught:
        await make_provider(recorder, timeout=0.1).complete(MESSAGES, PARAMS)

    assert str(caught.value) == 'timeout'


async def test_an_answer_that_ends_too_early_is_interrupted():
    recorder = streaming(sse(piece('엔진 소리가 ')))

    with pytest.raises(ProviderError) as caught:
        await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert str(caught.value) == 'interrupted'


async def test_an_answer_that_is_not_a_stream_is_interrupted():
    # 프록시가 200 으로 HTML 을 돌려준 경우. 데이터 줄이 하나도 없다
    recorder = Recorder(lambda request: httpx.Response(200, text='<html>proxy error</html>'))

    with pytest.raises(ProviderError) as caught:
        await make_provider(recorder).complete(MESSAGES, PARAMS)

    assert str(caught.value) == 'interrupted'
