# shared/server-core/src/server_core/input_errors.py

"""
입력 오류(요청의 칸이 틀렸다)의 응답과 API 목록의 모양.

오류의 본문은 서버마다 같다(docs/api/README.md 의 "오류의 모양"). 화면은 상태 코드가 아니라 errors 칸이 있는지로
입력 오류를 알아본다(web/apps/web/src/api/errors.ts).

    { "detail": "입력이 올바르지 않습니다.", "errors": { "action.kind": ["Field required"] } }

FastAPI 의 기본 본문({"detail": [{loc, msg, type, input, ctx}]})은 쓰지 않는다.
  - detail 이 글이 아니어서 화면이 다른 서버와 같은 코드로 읽지 못한다
  - input 에는 사용자가 보낸 값이 그대로 들어 있다. 응답으로 되돌리지 않는다

상태 코드는 그 서버의 계약이다. FastAPI 서버들은 422 를 지킨다. 프레임워크를 바꿔도 서버가 정한 코드를 바꾸지 않는다.
"""

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# 입력이 틀렸을 때의 문장. 어느 칸이 왜 틀렸는지는 errors 에 싣는다
INVALID_INPUT_DETAIL = '입력이 올바르지 않습니다.'

# API 목록에서 입력 오류의 본문 이름
INPUT_ERROR_SCHEMA = 'InputError'

# FastAPI 가 적는 입력 오류의 모양. 이 이름들을 InputError 로 바꾼다
FASTAPI_VALIDATION_SCHEMAS = ('HTTPValidationError', 'ValidationError')

# loc 의 첫 칸이 이것이면 어디서 온 값인지일 뿐이라 칸의 이름에서 뺀다
LOCATION_ROOTS = frozenset({'body', 'query', 'path', 'header', 'cookie'})

# 서버들이 지키는 입력 오류의 코드
DEFAULT_STATUS_CODE = status.HTTP_422_UNPROCESSABLE_CONTENT

# 본문이 JSON 이 아니다. loc 의 둘째 칸은 칸이 아니라 글자의 자리라서 칸의 이름을 body 로 둔다
JSON_INVALID_TYPE = 'json_invalid'
WHOLE_BODY_FIELD = 'body'


def field_name(error: Mapping[str, Any]) -> str:
    """틀린 칸의 이름. loc 를 점으로 잇는다(action.kind, items.0.name). 어디서 온 값인지(body 등)는 뺀다."""
    loc = tuple(error.get('loc') or ())
    if error.get('type') == JSON_INVALID_TYPE:
        return WHOLE_BODY_FIELD
    parts = loc[1:] if loc and loc[0] in LOCATION_ROOTS else loc
    if not parts:
        return str(loc[0]) if loc else WHOLE_BODY_FIELD
    return '.'.join(str(part) for part in parts)


def field_errors(errors: Iterable[Mapping[str, Any]]) -> dict[str, list[str]]:
    """칸의 이름마다 틀린 까닭들. 까닭은 검사기의 글(msg)만 싣고 보낸 값(input, ctx)은 싣지 않는다."""
    fields: dict[str, list[str]] = {}
    for error in errors:
        message = error.get('msg')
        if isinstance(message, str) and message:
            fields.setdefault(field_name(error), []).append(message)
    return fields


def input_error_body(errors: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """입력 오류의 본문."""
    return {'detail': INVALID_INPUT_DETAIL, 'errors': field_errors(errors)}


def input_error_handler(status_code: int) -> Callable[[Request, Exception], Any]:
    """RequestValidationError 를 이 서버의 입력 오류 응답(status_code)으로 바꾸는 처리기."""

    async def handle_invalid_input(request: Request, exc: Exception) -> JSONResponse:
        errors = exc.errors() if isinstance(exc, RequestValidationError) else []
        return JSONResponse(status_code=status_code, content=input_error_body(errors))

    return handle_invalid_input


def input_error_schema() -> dict[str, Any]:
    """API 목록에 적는 입력 오류 본문의 모양."""
    return {
        'title': INPUT_ERROR_SCHEMA,
        'type': 'object',
        'required': ['detail', 'errors'],
        'properties': {
            'detail': {'type': 'string', 'description': '무엇이 잘못됐는가. 화면에 그대로 보여 줄 수 있는 문장이다'},
            'errors': {
                'type': 'object',
                'additionalProperties': {'type': 'array', 'items': {'type': 'string'}},
                'description': '칸의 이름(점으로 이은 경로)마다 틀린 까닭들이다',
            },
        },
    }


def _schema_ref(name: str) -> str:
    return f'#/components/schemas/{name}'


def _uses_fastapi_validation(response: Mapping[str, Any]) -> bool:
    schema = response.get('content', {}).get('application/json', {}).get('schema', {})
    return schema.get('$ref') == _schema_ref(FASTAPI_VALIDATION_SCHEMAS[0])


def _replace_operation_responses(responses: dict[str, Any], status_code: int) -> None:
    """요청 하나의 응답에서 FastAPI 의 입력 오류를 InputError 로 바꾼다. 서버가 직접 적은 응답은 두지 않는다."""
    original = responses.get('422')
    if not isinstance(original, dict) or not _uses_fastapi_validation(original):
        return
    del responses['422']
    responses.setdefault(
        str(status_code),
        {
            'description': '입력이 틀렸다',
            'content': {'application/json': {'schema': {'$ref': _schema_ref(INPUT_ERROR_SCHEMA)}}},
        },
    )


def _is_referenced(schema: dict[str, Any], name: str) -> bool:
    """목록 안 어디선가 그 모양을 가리키는가. 모양 자신의 정의는 세지 않는다."""
    target = _schema_ref(name)
    stack: list[Any] = [value for key, value in schema.items() if key != 'components']
    stack.extend(value for key, value in schema.get('components', {}).get('schemas', {}).items() if key != name)
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get('$ref') == target:
                return True
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return False


def replace_validation_schemas(schema: dict[str, Any], status_code: int = DEFAULT_STATUS_CODE) -> None:
    """API 목록의 입력 오류를 InputError 로 바꾼다(자리에서 고친다). 더는 쓰지 않는 FastAPI 의 모양은 지운다."""
    for path_item in schema.get('paths', {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict) and isinstance(operation.get('responses'), dict):
                _replace_operation_responses(operation['responses'], status_code)
    components = schema.setdefault('components', {}).setdefault('schemas', {})
    components[INPUT_ERROR_SCHEMA] = input_error_schema()
    for name in FASTAPI_VALIDATION_SCHEMAS:
        if name in components and not _is_referenced(schema, name):
            del components[name]


def use_input_errors(app: FastAPI, status_code: int = DEFAULT_STATUS_CODE) -> None:
    """
    앱의 입력 오류를 공통 본문으로 답하고 API 목록에도 그 모양을 적는다. 앱을 만들 때 한 번 부른다.

    status_code 는 그 서버가 정해 둔 입력 오류의 코드다. FastAPI 서버들은 422 다.
    """
    app.add_exception_handler(RequestValidationError, input_error_handler(status_code))
    build_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = build_openapi()
        replace_validation_schemas(schema, status_code)
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
