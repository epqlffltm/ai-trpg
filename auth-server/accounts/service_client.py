# auth-server/accounts/service_client.py

"""
우리 서버끼리의 요청 하나를 서명해 보낸다.
결제 서버를 부르는 것(billing_client.py)과 탈퇴를 알리는 것(withdrawal_client.py)이 쓴다.

요청마다 서명을 붙인다(service_signature.py). 받는 서버가 그것으로 인증 서버임을 확인한다.
이 모듈은 보내고 상태 코드와 본문을 돌려주는 일만 한다.
답을 어떻게 읽는지, 실패하면 언제 다시 보내는지는 부르는 쪽이 정한다.
"""

import time
import urllib.error
import urllib.request

from accounts.service_signature import SIGNATURE_HEADER, sign_request
from observability.context import outgoing_headers
from observability.http_spans import client_span, mark_unreachable, record_status

# 받는 서버의 답을 기다리는 가장 긴 시간(초). 워커가 죽은 서버를 무한정 기다리지 않게 한다
TIMEOUT_SECONDS = 5


class ServiceUnavailableError(Exception):
    """
    다른 서버에 요청을 보내지 못했다. 나중에 다시 보내면 될 수 있다.

    닿지 못했거나, 시간 안에 답이 없었거나, 이 서버의 설정(비밀)이 빠진 경우다.
    글에는 오류의 종류만 싣는다. 주소, 비밀, 서명은 싣지 않는다.
    """


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """다른 주소로 가라는 답을 따라가지 않는다. 서명한 요청이 우리가 고르지 않은 곳으로 가면 안 된다."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def post_signed(
    *,
    base_url: str,
    secret: str,
    secret_name: str,
    path: str,
    body: bytes,
    error: type[ServiceUnavailableError] = ServiceUnavailableError,
) -> tuple[int, bytes]:
    """
    서명한 POST 를 base_url + path 로 보내고 상태 코드와 본문을 돌려준다. 닿지 못하면 error 다.

    4xx 와 5xx 도 답을 받은 것이다. 상태 코드로 돌려준다(본문은 비운다). 받아들일지는 부르는 쪽이 정한다.
    작업 안에서 부르면 client span 을 건다(observability/http_spans.py). 머리말을 그 안에서 만들어
    traceparent 가 그 span 을 부모로 가리킨다. 받는 서버의 span 이 그 아래에 붙는다.
    """
    url = base_url + path
    with client_span('POST', url) as span:
        request = urllib.request.Request(
            url, data=body, method='POST', headers=_headers(secret, secret_name, path, body, error)
        )
        try:
            with _opener().open(request, timeout=TIMEOUT_SECONDS) as response:
                record_status(span, response.status)
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            # 4xx 와 5xx 는 예외로 온다. 답은 받은 것이다
            record_status(span, exc.code)
            return exc.code, b''
        except OSError as exc:
            # 연결 실패와 시간 초과를 포함한다. 오류의 글에는 주소가 들어 있을 수 있어 종류만 적는다
            mark_unreachable(span)
            raise error(f'닿지 못했다: {type(exc).__name__}') from exc


def _headers(
    secret: str, secret_name: str, path: str, body: bytes, error: type[ServiceUnavailableError]
) -> dict[str, str]:
    """요청에 붙일 머리말. 서명과, 추적을 이어 주는 값이다. 비밀이 없으면 보내지 않고 error 다."""
    if not secret:
        raise error(f'{secret_name} 이 없다')
    signature = sign_request(secret=secret, method='POST', request_uri=path, body=body, sent_at=int(time.time()))
    return {'Content-Type': 'application/json', SIGNATURE_HEADER: signature, **outgoing_headers()}


def _opener() -> urllib.request.OpenerDirector:
    """
    요청을 보낼 때 쓰는 것. 환경 변수의 프록시를 쓰지 않고, 다른 주소로 가라는 답을 따라가지 않는다.

    우리 서버끼리의 요청이다. 개발자의 PC 에 잡힌 프록시(HTTP_PROXY)를 거쳐 나가면 안 된다.
    """
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
