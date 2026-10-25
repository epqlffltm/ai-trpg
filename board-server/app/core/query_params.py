# board-server/app/core/query_params.py

"""
주소에 붙은 값(?page=2&q=주사위)을 요청 모델로 읽는다.

FastAPI 가 쿼리 모델을 읽을 때는 같은 이름을 여러 번 보내면 마지막 값만 남긴다.
NestJS 로 쓰던 때는 그것을 목록으로 받아 거부했다(?q=주사위&q=버그 는 400). 그 계약을 지키려고 직접 읽는다.
  - 한 번 온 이름은 글자, 여러 번 온 이름은 글자의 목록으로 모델에 넘긴다. 목록은 모델의 검사가 거부한다
  - 모델의 오류는 FastAPI 의 입력 오류(RequestValidationError)로 바꾼다. 응답의 모양은 app/core/errors.py 가 만든다
  - API 목록에는 모델의 칸을 쿼리 값으로 적는다(query_parameters). FastAPI 가 스스로 적지 못해서다
"""

from collections.abc import Callable
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from server_core.input_errors import INPUT_ERROR_SCHEMA

# API 목록에 적는 입력 오류의 응답. 다른 주소의 것(app/core/errors.py 가 바꾼 것)과 같은 모양이다
INPUT_ERROR_RESPONSE = {
    'description': '입력이 틀렸다',
    'content': {'application/json': {'schema': {'$ref': f'#/components/schemas/{INPUT_ERROR_SCHEMA}'}}},
}

# 오류의 위치 앞에 붙이는 이름. 칸 이름을 만들 때 빠진다
QUERY_LOCATION = 'query'


def raw_query(request: Request) -> dict[str, str | list[str]]:
    """주소의 값들. 여러 번 온 이름은 목록이다."""
    raw: dict[str, str | list[str]] = {}
    for key in request.query_params:
        values = request.query_params.getlist(key)
        raw[key] = values[0] if len(values) == 1 else values
    return raw


def query_errors(error: ValidationError) -> list[dict[str, Any]]:
    """모델의 오류를 쿼리 값의 오류로. 위치 앞에 query 를 붙인다."""
    return [
        {'type': item['type'], 'loc': (QUERY_LOCATION, *item['loc']), 'msg': item['msg']} for item in error.errors()
    ]


def query_model[Model: BaseModel](model: type[Model]) -> Callable[[Request], Model]:
    """주소의 값을 model 로 읽는 의존성."""

    def read(request: Request) -> Model:
        try:
            return model.model_validate(raw_query(request))
        except ValidationError as error:
            raise RequestValidationError(query_errors(error)) from error

    return read


def query_parameters(model: type[BaseModel]) -> dict[str, Any]:
    """
    API 목록에 적을 쿼리 값들(openapi_extra). 모델의 칸마다 하나다.

    쿼리를 직접 읽어서 FastAPI 가 입력 오류(400)를 스스로 적지 못한다. 그것도 함께 적는다.
    """
    schema = model.model_json_schema()
    required = set(schema.get('required', []))
    parameters = []
    for name, field in schema.get('properties', {}).items():
        description = field.pop('description', None)
        field.pop('title', None)
        parameter: dict[str, Any] = {'name': name, 'in': QUERY_LOCATION, 'required': name in required, 'schema': field}
        if description:
            parameter['description'] = description
        parameters.append(parameter)
    return {'parameters': parameters, 'responses': {'400': INPUT_ERROR_RESPONSE}}
