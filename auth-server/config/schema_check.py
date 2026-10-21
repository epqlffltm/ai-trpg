# auth-server/config/schema_check.py

"""
테스트가 받은 응답이 API 목록(OpenAPI, #558)과 맞는지 본다. 테스트 실행기(config/test_runner.py)가 건다.

목록은 뷰에 적은 모양(accounts/api_schema.py)에서 나온다. 적은 것이 코드와 어긋나면 그 응답을 받은 테스트가 실패한다.
  - 목록에 없는 상태 코드
  - 목록의 모양과 다른 본문(없는 칸, 더 붙은 칸, 다른 타입)

보지 않는 응답:
  - 목록에 없는 주소나 방식의 것(관리자 화면, HEAD, 405). 목록에 올리지 않은 것이다
  - 어느 주소에도 맞지 않은 404. 테스트가 따로 만든 URL 설정으로 도는 요청이다
  - 서버의 오류(500). 어느 주소든 낼 수 있고 본문은 Django 의 기본 오류 화면(HTML)이라 목록에 적지 않는다
  - 스트림으로 내는 응답(본문을 한 번에 읽을 수 없다)
  - 머리말에 줄바꿈을 넣은 요청의 응답. 검사하는 쪽(openapi-core)이 그 머리말을 읽지 못한다.
    그런 요청을 일부러 보내는 테스트가 있다

요청은 보지 않는다. 테스트는 일부러 틀린 요청을 보낸다. 그 답(400)이 목록의 모양인지만 본다.
테스트 밖에서는 이 파일을 쓰지 않는다. 서버는 요청마다 목록으로 검사하지 않는다.
"""

import json
from collections.abc import Callable

from django.http import HttpResponseBase
from django.test.client import Client
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.renderers import OpenApiJsonRenderer
from openapi_core import OpenAPI
from openapi_core.contrib.django import DjangoOpenAPIRequest, DjangoOpenAPIResponse
from openapi_core.templating.paths.exceptions import OperationNotFound, PathNotFound

# 서버의 오류. 목록에 적지 않는다(맨 위의 "보지 않는 응답")
SERVER_ERROR = 500


class SchemaMismatchError(AssertionError):
    """테스트가 받은 응답이 API 목록과 맞지 않다."""


def build_openapi() -> OpenAPI:
    """지금의 뷰에서 목록을 만들어 검사할 수 있게 읽는다. 저장소의 파일(docs/api)과 같은 것이다."""
    schema = SchemaGenerator().get_schema(request=None, public=True)
    return OpenAPI.from_dict(json.loads(OpenApiJsonRenderer().render(schema)))


def is_checkable(response: HttpResponseBase) -> bool:
    """
    볼 수 있는 응답인가. 테스트 클라이언트가 만든 요청이 붙어 있고, 어느 주소가 답했고,
    서버의 오류가 아니고, 본문을 한 번에 읽을 수 있어야 한다.
    """
    request = getattr(response, 'wsgi_request', None)
    return (
        request is not None
        and request.resolver_match is not None
        and response.status_code != SERVER_ERROR
        and not response.streaming
    )


def openapi_request(response: HttpResponseBase) -> DjangoOpenAPIRequest | None:
    """검사하는 쪽에 넘길 요청. 머리말을 읽을 수 없으면(줄바꿈이 든 머리말) None 이다."""
    try:
        return DjangoOpenAPIRequest(response.wsgi_request)
    except ValueError:
        return None


def mismatch_message(response: HttpResponseBase, error: Exception) -> str:
    """맞지 않을 때의 글. 무엇을 고칠지 찾을 수 있게 주소, 상태 코드, 본문을 싣는다."""
    request = response.wsgi_request
    body = response.content.decode('utf-8', errors='replace')[:500]
    return (
        f'{request.method} {request.path} 의 응답({response.status_code})이 API 목록과 맞지 않다: {error!r}\n'
        f'본문: {body}\n'
        f'accounts/api_schema.py 와 뷰의 @extend_schema 를 고친다'
    )


def check_response(openapi: OpenAPI, response: HttpResponseBase) -> None:
    """응답이 목록과 맞는지 본다. 맞지 않으면 SchemaMismatchError. 목록에 없는 주소와 방식은 보지 않는다."""
    if not is_checkable(response):
        return
    request = openapi_request(response)
    if request is None:
        return
    try:
        openapi.validate_response(request, DjangoOpenAPIResponse(response))
    except (PathNotFound, OperationNotFound):
        return
    except Exception as error:
        raise SchemaMismatchError(mismatch_message(response, error)) from error


def start_checking(openapi: OpenAPI) -> Callable[[], None]:
    """
    테스트 클라이언트가 받는 모든 응답을 목록과 견주기 시작한다. 멈추는 함수를 돌려준다.

    Django 의 테스트 클라이언트(DRF 의 APIClient 도 이것을 거친다)의 request 를 감싼다.
    테스트 파일마다 고치지 않아도 모든 HTTP 테스트가 견준다.
    """
    original = Client.request

    def request(self: Client, **kwargs) -> HttpResponseBase:
        response = original(self, **kwargs)
        check_response(openapi, response)
        return response

    Client.request = request

    def stop() -> None:
        Client.request = original

    return stop
