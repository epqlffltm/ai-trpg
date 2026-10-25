# board-server/tests/test_errors.py

"""
오류 응답의 모양(app/core/errors.py)을 검증한다. 시험용 주소를 앱에 더해 본다.

  - 이 서버의 거절(ApiError)은 {"detail"}, 기다릴 초가 있으면 본문과 Retry-After 에 싣는다
  - 라이브러리의 거절(없는 주소, 허용하지 않는 메서드)은 이 서버의 문장으로 바꾼다
  - 입력 오류는 400 {"detail", "errors"}, 본문이 JSON 이 아니면 400 {"detail"} 이다
  - API 목록의 입력 오류는 400 의 InputError 다
"""

from typing import Annotated

import pytest
from fastapi import FastAPI, HTTPException, Query, status
from httpx import AsyncClient
from pydantic import BaseModel, ConfigDict

from app.core.errors import ApiError, default_detail, detail_of
from tests.conftest import make_client

PROBE = '/api/v1/board/probe'


class ProbeBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: str


@pytest.fixture
def probed(app: FastAPI) -> FastAPI:
    """거절을 일부러 내는 시험용 주소를 더한 앱."""

    @app.get(f'{PROBE}/limited', status_code=status.HTTP_200_OK)
    async def limited() -> None:
        raise ApiError(status.HTTP_429_TOO_MANY_REQUESTS, '너무 자주 썼다', retry_after=42)

    @app.get(f'{PROBE}/forbidden', status_code=status.HTTP_200_OK)
    async def forbidden() -> None:
        raise ApiError(status.HTTP_403_FORBIDDEN, '운영자만 쓸 수 있습니다.')

    @app.get(f'{PROBE}/plain', status_code=status.HTTP_200_OK)
    async def plain() -> None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)

    @app.post(f'{PROBE}/body', status_code=status.HTTP_201_CREATED)
    async def body(payload: ProbeBody) -> dict[str, str]:
        return {'title': payload.title}

    @app.get(f'{PROBE}/query', status_code=status.HTTP_200_OK)
    async def query(page: Annotated[int, Query(ge=1)] = 1) -> dict[str, int]:
        return {'page': page}

    app.openapi_schema = None
    return app


@pytest.fixture
async def probe_client(probed: FastAPI):
    async with make_client(probed) as client:
        yield client


async def test_a_refusal_with_retry_after_puts_it_in_the_body_and_header(probe_client: AsyncClient):
    response = await probe_client.get(f'{PROBE}/limited')

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json() == {'detail': '너무 자주 썼다', 'retry_after': 42}
    assert response.headers['Retry-After'] == '42'


async def test_a_refusal_carries_only_its_sentence(probe_client: AsyncClient):
    response = await probe_client.get(f'{PROBE}/forbidden')

    assert response.json() == {'detail': '운영자만 쓸 수 있습니다.'}
    assert 'Retry-After' not in response.headers


async def test_a_library_refusal_gets_this_servers_sentence(probe_client: AsyncClient):
    response = await probe_client.get(f'{PROBE}/plain')

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {'detail': '요청이 지금 상태와 맞지 않습니다.'}


async def test_an_unknown_path_is_404_with_this_servers_sentence(client: AsyncClient):
    response = await client.get('/api/v1/board/no-such-api')

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {'detail': '찾을 수 없습니다.'}


async def test_a_method_not_allowed_is_405_with_this_servers_sentence(client: AsyncClient):
    response = await client.delete('/api/v1/board/boards')

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    assert response.json() == {'detail': '허용되지 않는 요청입니다.'}


async def test_a_wrong_field_is_400_with_field_errors(probe_client: AsyncClient):
    response = await probe_client.post(f'{PROBE}/body', json={'title': '글', 'colour': 'red'})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    assert body['detail'] == '입력이 올바르지 않습니다.'
    assert set(body['errors']) == {'colour'}


async def test_a_wrong_query_is_400_with_the_query_name(probe_client: AsyncClient):
    response = await probe_client.get(f'{PROBE}/query', params={'page': 0})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert set(response.json()['errors']) == {'page'}


async def test_a_broken_json_body_is_400_without_the_parser_message(probe_client: AsyncClient):
    response = await probe_client.post(
        f'{PROBE}/body', content=b'{"title": ', headers={'Content-Type': 'application/json'}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {'detail': '요청이 올바르지 않습니다.'}


def test_the_api_list_writes_input_errors_as_400(probed: FastAPI):
    responses = probed.openapi()['paths'][f'{PROBE}/body']['post']['responses']

    assert '422' not in responses
    assert responses['400']['content']['application/json']['schema']['$ref'].endswith('InputError')


@pytest.mark.parametrize(
    ('status_code', 'detail'),
    [(418, '요청을 처리할 수 없습니다.'), (502, '서버에서 오류가 났습니다.'), (404, '찾을 수 없습니다.')],
)
def test_default_sentences(status_code: int, detail: str):
    assert default_detail(status_code) == detail


def test_an_unknown_status_code_keeps_a_written_sentence():
    assert detail_of(599, '알 수 없는 상태') == '알 수 없는 상태'
    assert detail_of(404, None) == '찾을 수 없습니다.'
