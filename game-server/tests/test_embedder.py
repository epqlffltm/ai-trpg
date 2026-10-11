# game-server/tests/test_embedder.py

"""
임베더를 검증한다.
OpenAI 모양의 임베더(app/ai/openai_embedder.py), 가짜 임베더(app/ai/fake.py), 고르는 규칙(app/lore/setup.py).

실제 모델을 부르지 않는다. httpx 의 가짜 전송(MockTransport)이 Ollama 인 척 답한다.
"""

import asyncio
import json
import math
from collections.abc import Callable

import httpx
import pytest

from app.ai.fake import FAKE_DIMENSIONS, FakeEmbedder, word_vector
from app.ai.openai_embedder import OpenAICompatEmbedder, embeddings_url, read_vectors
from app.ai.provider import ProviderError
from app.lore.setup import build_embedder
from tests.conftest import make_test_settings

BASE_URL = 'http://127.0.0.1:11434/v1'
MODEL = 'bge-m3'
TEXTS = ['엘프 폭주족', '드워프의 망치']
# 응답 본문에 되돌아온 보낸 글. 오류 메시지에 실리면 안 된다
SECRET = '악역영애는 사실 경찰의 끄나풀이다.'


def make_answer(*vectors: list[float], reverse: bool = False) -> dict:
    """Ollama 가 돌려주는 모양의 답. reverse 면 data 의 차례를 뒤집어 보낸다."""
    data = [{'object': 'embedding', 'index': index, 'embedding': vector} for index, vector in enumerate(vectors)]
    if reverse:
        data.reverse()
    return {'object': 'list', 'model': MODEL, 'data': data}


class Recorder:
    """가짜 전송이 받은 요청을 적어 두고, 정해 둔 답을 돌려준다."""

    def __init__(self, respond: Callable[[httpx.Request], httpx.Response]):
        self.respond = respond
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.respond(request)


def answering(answer: dict, status: int = 200) -> Recorder:
    return Recorder(lambda request: httpx.Response(status, json=answer))


def make_embedder(recorder: Callable, **overrides) -> OpenAICompatEmbedder:
    client = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    values = {'client': client, 'base_url': BASE_URL, 'model': MODEL}
    values.update(overrides)
    return OpenAICompatEmbedder(**values)


# --- OpenAI 모양의 임베더 ---


@pytest.mark.parametrize('base_url', [BASE_URL, f'{BASE_URL}/'])
def test_the_address_ends_with_embeddings(base_url: str):
    assert embeddings_url(base_url) == f'{BASE_URL}/embeddings'


async def test_the_texts_go_in_one_request():
    recorder = answering(make_answer([0.1, 0.2], [0.3, 0.4]))

    await make_embedder(recorder).embed(TEXTS)

    (request,) = recorder.requests
    assert str(request.url) == f'{BASE_URL}/embeddings'
    assert json.loads(request.content) == {'model': MODEL, 'input': TEXTS}


async def test_the_vectors_come_back_in_the_order_sent():
    # 서버가 data 의 차례를 섞어 보내도 index 로 맞춘다
    recorder = answering(make_answer([0.1, 0.2], [0.3, 0.4], reverse=True))

    vectors = await make_embedder(recorder).embed(TEXTS)

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


async def test_whole_numbers_become_floats():
    vectors = await make_embedder(answering(make_answer([1, 0]))).embed(['가'])

    assert vectors == [[1.0, 0.0]]
    assert all(isinstance(number, float) for number in vectors[0])


async def test_no_texts_send_nothing():
    recorder = answering(make_answer())

    assert await make_embedder(recorder).embed([]) == []
    assert recorder.requests == []


@pytest.mark.parametrize('status', [400, 404, 500, 503])
async def test_an_error_status_is_a_provider_error(status: int):
    recorder = answering({'error': {'message': SECRET}}, status=status)

    with pytest.raises(ProviderError) as caught:
        await make_embedder(recorder).embed(TEXTS)

    assert str(caught.value) == f'status_{status}'
    assert SECRET not in str(caught.value)


async def test_a_refused_connection_is_unreachable():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('연결 거부', request=request)

    with pytest.raises(ProviderError) as caught:
        await make_embedder(refuse).embed(TEXTS)

    assert str(caught.value) == 'unreachable'


async def test_a_timeout_is_a_provider_error():
    def hang(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout('시간 초과', request=request)

    with pytest.raises(ProviderError) as caught:
        await make_embedder(hang).embed(TEXTS)

    assert str(caught.value) == 'timeout'


async def test_the_whole_call_has_a_time_limit():
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.5)
        return httpx.Response(200, json=make_answer([0.1], [0.2]))

    with pytest.raises(ProviderError) as caught:
        await make_embedder(slow, timeout=0.05).embed(TEXTS)

    assert str(caught.value) == 'timeout'


async def test_an_answer_that_is_not_json_is_a_provider_error():
    recorder = Recorder(lambda request: httpx.Response(200, text='<html>proxy error</html>'))

    with pytest.raises(ProviderError) as caught:
        await make_embedder(recorder).embed(TEXTS)

    assert str(caught.value) == 'not_json'


@pytest.mark.parametrize(
    'data',
    [
        {},
        {'data': 'text'},
        {'data': [{'embedding': [0.1]}]},
        # 보낸 글은 둘인데 벡터는 하나다
        make_answer([0.1, 0.2]),
        make_answer([0.1, 0.2], []),
        make_answer([0.1, 0.2], ['a', 'b']),
        make_answer([0.1, 0.2], [True, False]),
        # 벡터마다 길이가 다르다
        make_answer([0.1, 0.2], [0.3]),
        [],
    ],
)
def test_an_answer_of_the_wrong_shape_is_malformed(data):
    with pytest.raises(ProviderError) as caught:
        read_vectors(data, len(TEXTS))

    assert str(caught.value) == 'malformed'


def indexed(*indices) -> dict:
    """index 를 마음대로 적은 답. 벡터는 index 마다 멀쩡한 것이다."""
    data = [{'index': index, 'embedding': [0.1, 0.2]} for index in indices]
    return {'object': 'list', 'model': MODEL, 'data': data}


@pytest.mark.parametrize(
    'indices',
    [
        # 같은 차례가 둘이다. 개수는 맞지만 한 글의 벡터가 없다
        (0, 0),
        (1, 1),
        # 범위 밖이다
        (0, 9),
        (-1, 0),
        (1, 2),
        # 정수가 아니다. True 는 파이썬에서 1 과 같지만 차례가 아니다
        (0, True),
        (0, 1.0),
        (0, '1'),
        (0, None),
    ],
)
def test_an_answer_whose_order_cannot_be_trusted_is_malformed(indices: tuple):
    with pytest.raises(ProviderError) as caught:
        read_vectors(indexed(*indices), len(TEXTS))

    assert str(caught.value) == 'malformed'


def test_an_answer_with_too_many_vectors_is_malformed():
    with pytest.raises(ProviderError) as caught:
        read_vectors(indexed(0, 1, 2), len(TEXTS))

    assert str(caught.value) == 'malformed'


def test_an_answer_out_of_order_is_put_back_in_order():
    answer = {'data': [{'index': 1, 'embedding': [0.3, 0.4]}, {'index': 0, 'embedding': [0.1, 0.2]}]}

    assert read_vectors(answer, len(TEXTS)) == [[0.1, 0.2], [0.3, 0.4]]


@pytest.mark.parametrize(
    'broken',
    [
        # 유한하지 않은 숫자. JSON 에는 없지만 파이썬은 NaN, Infinity 를 읽어 준다
        [math.nan, 0.2],
        [0.1, math.inf],
        [-math.inf, 0.2],
        # 실수로 바꿀 수 없을 만큼 큰 정수
        [10**400, 0.2],
        # 모두 0 이다. 방향이 없어 거리를 잴 수 없다
        [0.0, 0.0],
        [0, 0],
    ],
)
def test_a_vector_that_cannot_be_compared_is_malformed(broken: list):
    with pytest.raises(ProviderError) as caught:
        read_vectors(make_answer([0.1, 0.2], broken), len(TEXTS))

    assert str(caught.value) == 'malformed'


def test_a_vector_with_some_zeros_is_fine():
    assert read_vectors(make_answer([0.0, 0.2], [0.3, 0.0]), len(TEXTS)) == [[0.0, 0.2], [0.3, 0.0]]


async def test_nan_in_the_body_is_refused_end_to_end():
    # 서버가 JSON 이 아닌 NaN 을 그대로 적어 보냈다. 본문을 읽는 데서 걸리지 않으므로 벡터를 검사해서 막는다
    body = '{"data": [{"index": 0, "embedding": [NaN, 0.2]}, {"index": 1, "embedding": [0.3, 0.4]}]}'
    recorder = Recorder(lambda request: httpx.Response(200, content=body, headers={'content-type': 'application/json'}))

    with pytest.raises(ProviderError) as caught:
        await make_embedder(recorder).embed(TEXTS)

    assert str(caught.value) == 'malformed'


def test_the_length_is_not_checked_unless_it_is_set():
    assert read_vectors(make_answer([0.1, 0.2], [0.3, 0.4]), len(TEXTS)) == [[0.1, 0.2], [0.3, 0.4]]
    assert read_vectors(make_answer([0.1, 0.2], [0.3, 0.4]), len(TEXTS), dimensions=2) == [[0.1, 0.2], [0.3, 0.4]]


def test_vectors_of_another_length_than_the_set_one_are_malformed():
    # 벡터끼리는 길이가 같다. 그래도 정해 둔 길이가 아니면, 이미 저장한 벡터와 견줄 수 없다
    with pytest.raises(ProviderError) as caught:
        read_vectors(make_answer([0.1, 0.2], [0.3, 0.4]), len(TEXTS), dimensions=3)

    assert str(caught.value) == 'malformed'


async def test_the_embedder_refuses_another_length_than_the_one_it_was_given():
    embedder = make_embedder(answering(make_answer([0.1, 0.2], [0.3, 0.4])), dimensions=1024)

    with pytest.raises(ProviderError) as caught:
        await embedder.embed(TEXTS)

    assert str(caught.value) == 'malformed'


async def test_the_set_length_reaches_the_embedder():
    settings = make_test_settings(embedder='llm', embedding_dimensions=1024)

    async with httpx.AsyncClient() as client:
        embedder = build_embedder(settings, client)

    assert embedder.dimensions == 1024


# --- 가짜 임베더 ---


async def test_the_fake_gives_the_same_vector_for_the_same_text():
    first, second = FakeEmbedder(), FakeEmbedder()

    assert await first.embed(TEXTS) == await second.embed(TEXTS)


def test_the_fake_vectors_have_length_one():
    vector = word_vector('엘프 폭주족이 바이크를 몬다')

    assert len(vector) == FAKE_DIMENSIONS
    assert math.isclose(sum(number * number for number in vector), 1.0)


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def test_texts_sharing_words_are_closer():
    query = word_vector('엘프 폭주족 바이크')

    near = cosine(query, word_vector('엘프 폭주족의 바이크 은하'))
    far = cosine(query, word_vector('드워프의 망치와 톨게이트'))

    assert near > far


def test_a_text_without_words_still_has_a_direction():
    # 길이가 0 인 벡터는 거리를 잴 수 없다
    assert math.isclose(sum(number * number for number in word_vector('...!')), 1.0)


async def test_the_fake_can_fail_on_purpose():
    embedder = FakeEmbedder(error='unreachable')

    with pytest.raises(ProviderError) as caught:
        await embedder.embed(TEXTS)

    assert str(caught.value) == 'unreachable'
    assert embedder.calls == [TEXTS]


# --- 고르는 규칙 ---


async def test_the_fake_is_chosen_by_default():
    async with httpx.AsyncClient() as client:
        assert isinstance(build_embedder(make_test_settings(), client), FakeEmbedder)


async def test_the_model_is_chosen_for_llm():
    settings = make_test_settings(embedder='llm', embedding_model=' bge-m3 ', llm_base_url=BASE_URL)

    async with httpx.AsyncClient() as client:
        embedder = build_embedder(settings, client)

    assert isinstance(embedder, OpenAICompatEmbedder)
    assert (embedder.base_url, embedder.model, embedder.timeout) == (BASE_URL, 'bge-m3', 30.0)
