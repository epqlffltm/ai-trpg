# shared/server-core/tests/test_input_errors.py

"""
입력 오류의 응답과 API 목록의 모양(server_core/input_errors.py)을 검증한다. 작은 앱으로 본다. DB 없이 돈다.

  - 칸이 틀리면 422 + {"detail", "errors"}. 칸의 이름은 loc 를 점으로 이은 것이고 body/query/path 는 뺀다
  - 사용자가 보낸 값(input)과 ctx 는 응답에 없다
  - JSON 이 깨지면 칸의 이름이 body 다
  - 서버가 정한 코드(예: 400)로도 답할 수 있다
  - API 목록의 422 는 InputError 를 가리키고 FastAPI 의 모양(HTTPValidationError)은 남지 않는다
"""

from typing import Annotated

from fastapi import FastAPI, Query, status
from pydantic import BaseModel, Field

from server_core.input_errors import (
    INPUT_ERROR_SCHEMA,
    INVALID_INPUT_DETAIL,
    field_errors,
    field_name,
    use_input_errors,
)
from tests.conftest import make_client

SECRET_INPUT = 'secret-value-that-must-not-come-back'
OWN_SCHEMA = {'type': 'object'}


class Action(BaseModel):
    kind: Annotated[str, Field(min_length=3)]


class Declare(BaseModel):
    action: Action
    tags: list[Annotated[str, Field(max_length=5)]] = []


def build_app(status_code: int | None = None) -> FastAPI:
    app = FastAPI()
    if status_code is None:
        use_input_errors(app)
    else:
        use_input_errors(app, status_code=status_code)

    @app.post('/declare', status_code=status.HTTP_201_CREATED)
    async def declare(body: Declare) -> dict[str, str]:
        return {'kind': body.action.kind}

    @app.get('/items', status_code=status.HTTP_200_OK)
    async def items(limit: Annotated[int, Query(ge=1, le=50)] = 10) -> dict[str, int]:
        return {'limit': limit}

    return app


async def test_a_wrong_field_is_422_with_detail_and_errors():
    async with make_client(build_app()) as client:
        response = await client.post('/declare', json={'action': {'kind': 'x'}, 'tags': ['ok', 'too-long']})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    body = response.json()
    assert body['detail'] == INVALID_INPUT_DETAIL
    assert set(body['errors']) == {'action.kind', 'tags.1'}
    assert all(isinstance(message, str) for messages in body['errors'].values() for message in messages)


async def test_the_sent_value_does_not_come_back():
    async with make_client(build_app()) as client:
        body = {'action': {'kind': 1}, 'note': SECRET_INPUT, 'tags': [SECRET_INPUT]}
        response = await client.post('/declare', json=body)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert SECRET_INPUT not in response.text
    assert set(response.json()) == {'detail', 'errors'}


async def test_a_wrong_query_drops_the_location():
    async with make_client(build_app()) as client:
        response = await client.get('/items', params={'limit': 99})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert set(response.json()['errors']) == {'limit'}


async def test_a_broken_json_body_is_the_body_field():
    async with make_client(build_app()) as client:
        response = await client.post('/declare', content=b'{"action": ', headers={'Content-Type': 'application/json'})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert set(response.json()['errors']) == {'body'}


async def test_a_server_can_keep_its_own_status_code():
    async with make_client(build_app(status_code=status.HTTP_400_BAD_REQUEST)) as client:
        response = await client.post('/declare', json={})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert set(response.json()['errors']) == {'action'}


def test_the_api_list_points_to_input_error():
    schema = build_app().openapi()

    responses = schema['paths']['/declare']['post']['responses']
    assert responses['422']['content']['application/json']['schema'] == {
        '$ref': f'#/components/schemas/{INPUT_ERROR_SCHEMA}'
    }
    components = schema['components']['schemas']
    assert INPUT_ERROR_SCHEMA in components
    assert 'HTTPValidationError' not in components
    assert 'ValidationError' not in components


def test_the_api_list_uses_the_servers_status_code():
    schema = build_app(status_code=status.HTTP_400_BAD_REQUEST).openapi()

    responses = schema['paths']['/declare']['post']['responses']
    assert '422' not in responses
    assert responses['400']['content']['application/json']['schema']['$ref'].endswith(INPUT_ERROR_SCHEMA)


def test_the_api_list_is_built_once():
    app = build_app()

    assert app.openapi() is app.openapi()


def test_a_response_the_server_wrote_itself_stays():
    app = build_app()

    @app.post(
        '/own',
        status_code=status.HTTP_201_CREATED,
        responses={422: {'description': '서버가 적은 거절', 'content': {'application/json': {'schema': OWN_SCHEMA}}}},
    )
    async def own() -> dict[str, str]:
        return {}

    responses = app.openapi()['paths']['/own']['post']['responses']
    assert responses['422']['description'] == '서버가 적은 거절'


def test_field_names():
    assert field_name({'loc': ('body', 'action', 'kind'), 'type': 'missing'}) == 'action.kind'
    assert field_name({'loc': ('path', 'table_id'), 'type': 'uuid_parsing'}) == 'table_id'
    assert field_name({'loc': ('body',), 'type': 'missing'}) == 'body'
    assert field_name({'loc': ('body', 12), 'type': 'json_invalid'}) == 'body'
    # 서버가 직접 검사해 던진 것(탈퇴 받기)은 loc 에 어디서 온 값인지가 없다
    assert field_name({'loc': ('withdrawn_at',), 'type': 'missing'}) == 'withdrawn_at'
    assert field_name({'loc': (), 'type': 'missing'}) == 'body'


def test_field_errors_groups_messages_by_field():
    errors = [
        {'loc': ('body', 'name'), 'msg': 'too short', 'type': 'string_too_short', 'input': 'a'},
        {'loc': ('body', 'name'), 'msg': 'bad pattern', 'type': 'string_pattern_mismatch', 'input': 'a'},
        {'loc': ('body', 'age'), 'msg': '', 'type': 'int_parsing', 'input': 'x'},
    ]

    assert field_errors(errors) == {'name': ['too short', 'bad pattern']}
