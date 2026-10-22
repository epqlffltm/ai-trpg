# asset-server/tests/test_image_store.py

"""
S3 의 서명(app/images/sigv4.py)과 그림 저장소(app/images/store.py, app/images/setup.py)를 검증한다.
네트워크를 쓰지 않는다(httpx.MockTransport). 실제 저장소(SeaweedFS)에 넣고 nginx 로 받는 것은 스택 시험이 본다.

보는 것.
  - 서명이 AWS 문서의 예시 값과 같다(서명한 주소, 머리말의 서명 둘. 경로의 인코딩 포함)
  - 넣기: 경로 방식의 주소, 형식, 본문의 해시, 서명. 2xx 가 아니거나 닿지 못하면 저장소를 쓸 수 없다
  - 서명한 주소: 저장소의 주소로 시작하고 60초 동안 산다. 서명을 다시 계산하면 같다
  - 설정: 주소가 비었으면 늘 503 인 저장소다. 주소 끝의 / 는 뗀다
"""

from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest

from app.images.setup import build_image_store
from app.images.sigv4 import (
    Credentials,
    authorization_header,
    canonical_query,
    presigned_query,
    sha256_hex,
    uri_encode,
)
from app.images.store import (
    PRESIGNED_SECONDS,
    ImageStoreUnavailableError,
    S3ImageStore,
    StoreLocation,
    UnconfiguredImageStore,
)
from tests.conftest import make_test_settings

# AWS 문서(Signature Version 4 의 예시)의 키와 시각
EXAMPLE = Credentials('AKIAIOSFODNN7EXAMPLE', 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY', 'us-east-1')
EXAMPLE_HOST = 'examplebucket.s3.amazonaws.com'
EXAMPLE_NOW = datetime(2013, 5, 24, tzinfo=UTC)

LOCAL = Credentials('ai-trpg-local', 'local-secret-0123456789', 'ap-northeast-2')
LOCATION = StoreLocation(origin='http://object-store:8333', bucket='ai-trpg-images')
NOW = datetime(2026, 10, 22, 1, 2, 3, tzinfo=UTC)
KEY = '0b7c6f1e-2d3a-4b5c-8d9e-0f1a2b3c4d5e'


def store_answering(handler) -> S3ImageStore:
    return S3ImageStore(httpx.AsyncClient(transport=httpx.MockTransport(handler)), LOCAL, LOCATION, 3.0)


# --- 서명 ---


def test_the_presigned_query_matches_the_aws_example():
    query = presigned_query(EXAMPLE, EXAMPLE_HOST, '/test.txt', 86400, EXAMPLE_NOW)

    assert query['X-Amz-Signature'] == 'aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404'
    assert query['X-Amz-Credential'] == 'AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request'


def test_the_header_signature_matches_the_aws_get_example():
    empty = sha256_hex(b'')
    headers = {
        'host': EXAMPLE_HOST,
        'range': 'bytes=0-9',
        'x-amz-content-sha256': empty,
        'x-amz-date': '20130524T000000Z',
    }

    value = authorization_header(EXAMPLE, 'GET', '/test.txt', headers, empty, EXAMPLE_NOW)

    assert value == (
        'AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request,'
        'SignedHeaders=host;range;x-amz-content-sha256;x-amz-date,'
        'Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41'
    )


def test_the_header_signature_matches_the_aws_put_example():
    # 경로의 $ 를 %24 로 인코딩해야 이 값이 나온다
    body = b'Welcome to Amazon S3.'
    headers = {
        'date': 'Fri, 24 May 2013 00:00:00 GMT',
        'host': EXAMPLE_HOST,
        'x-amz-content-sha256': sha256_hex(body),
        'x-amz-date': '20130524T000000Z',
        'x-amz-storage-class': 'REDUCED_REDUNDANCY',
    }

    value = authorization_header(EXAMPLE, 'PUT', '/test$file.text', headers, sha256_hex(body), EXAMPLE_NOW)

    assert value.endswith('Signature=98ad721746da40c64f1a55b78f14c238d841ea1380cd77a1b5971af0ece108bd')


def test_the_query_is_sorted_by_name():
    assert canonical_query({'b': '1', 'X-Amz-Date': '2', 'a b': '3'}) == 'X-Amz-Date=2&a%20b=3&b=1'


@pytest.mark.parametrize(
    ('value', 'keep_slash', 'expected'),
    [
        ('a-Z_0.9~', False, 'a-Z_0.9~'),
        ('a b/c', False, 'a%20b%2Fc'),
        ('/bucket/a b', True, '/bucket/a%20b'),
        ('AK/20130524', False, 'AK%2F20130524'),
    ],
)
def test_uri_encoding_keeps_only_unreserved(value: str, keep_slash: bool, expected: str):
    assert uri_encode(value, keep_slash) == expected


# --- 넣기 ---


async def test_put_sends_the_signed_object_to_the_bucket_path():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    await store_answering(handler).put(KEY, b'\x89PNG-bytes', 'image/png', NOW)

    (request,) = seen
    assert (request.method, str(request.url)) == ('PUT', f'http://object-store:8333/ai-trpg-images/{KEY}')
    assert request.content == b'\x89PNG-bytes'
    assert request.headers['content-type'] == 'image/png'
    assert request.headers['x-amz-content-sha256'] == sha256_hex(b'\x89PNG-bytes')
    assert request.headers['x-amz-date'] == '20261022T010203Z'
    assert request.extensions['timeout']['read'] == 3.0
    # 받은 머리말로 서명을 다시 계산하면 같다(저장소가 하는 일)
    signed = {name: request.headers[name] for name in ('content-type', 'host', 'x-amz-content-sha256', 'x-amz-date')}
    payload = request.headers['x-amz-content-sha256']
    expected = authorization_header(LOCAL, 'PUT', f'/ai-trpg-images/{KEY}', signed, payload, NOW)
    assert request.headers['authorization'] == expected
    assert signed['host'] == 'object-store:8333'


@pytest.mark.parametrize('status_code', [403, 404, 500, 503])
async def test_a_refusal_means_the_store_is_unavailable(status_code: int):
    store = store_answering(lambda request: httpx.Response(status_code, content=b'<Error><Code>Nope</Code></Error>'))

    with pytest.raises(ImageStoreUnavailableError) as caught:
        await store.put(KEY, b'x', 'image/png', NOW)

    # 저장소의 본문(XML)은 싣지 않는다
    assert 'Nope' not in str(caught.value)


async def test_not_reaching_the_store_means_it_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('닿지 않는다', request=request)

    with pytest.raises(ImageStoreUnavailableError):
        await store_answering(handler).put(KEY, b'x', 'image/png', NOW)


# --- 서명한 주소 ---


def test_the_presigned_url_points_at_the_object_for_sixty_seconds():
    url = store_answering(lambda request: httpx.Response(200)).presigned_get(KEY, NOW)

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    assert f'{parts.scheme}://{parts.netloc}{parts.path}' == f'http://object-store:8333/ai-trpg-images/{KEY}'
    assert (query['X-Amz-Expires'], query['X-Amz-SignedHeaders'], PRESIGNED_SECONDS) == ('60', 'host', 60)
    assert query['X-Amz-Credential'] == 'ai-trpg-local/20261022/ap-northeast-2/s3/aws4_request'
    # 서명을 빼고 다시 계산하면 같다
    signature = query.pop('X-Amz-Signature')
    assert presigned_query(LOCAL, 'object-store:8333', f'/ai-trpg-images/{KEY}', 60, NOW)['X-Amz-Signature'] == (
        signature
    )


# --- 설정 ---


async def test_without_an_endpoint_the_store_is_unavailable():
    store = build_image_store(make_test_settings(), httpx.AsyncClient())

    assert isinstance(store, UnconfiguredImageStore)
    with pytest.raises(ImageStoreUnavailableError):
        await store.put(KEY, b'x', 'image/png', NOW)
    with pytest.raises(ImageStoreUnavailableError):
        store.presigned_get(KEY, NOW)


def test_the_settings_build_an_s3_store():
    settings = make_test_settings(
        image_store_endpoint='https://s3.ap-northeast-2.amazonaws.com/',
        image_store_bucket='ai-trpg-images-staging',
        image_store_access_key_id='AKIA-TEST',
        image_store_secret_access_key='secret',
        image_store_timeout_seconds=7,
    )

    store = build_image_store(settings, httpx.AsyncClient())

    assert isinstance(store, S3ImageStore)
    assert store.location == StoreLocation('https://s3.ap-northeast-2.amazonaws.com', 'ai-trpg-images-staging')
    assert (store.credentials, store.timeout) == (Credentials('AKIA-TEST', 'secret', 'ap-northeast-2'), 7)
    assert store.presigned_get(KEY, NOW).startswith(
        f'https://s3.ap-northeast-2.amazonaws.com/ai-trpg-images-staging/{KEY}?'
    )
