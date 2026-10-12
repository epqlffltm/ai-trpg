# auth-server/accounts/billing_client.py

"""
결제 서버를 부른다. 지금 부르는 일은 하나다. 가입을 마친 사용자에게 환영 크레딧을 주라고 맡긴다.

요청마다 서명을 붙인다(service_signature.py). 결제 서버가 그것으로 인증 서버임을 확인한다.

이 모듈은 요청 하나를 보내고 결과를 돌려주는 일만 한다. 언제 부르는지, 실패하면 언제 다시 부르는지는
모른다. 그것은 welcome_credit.py 가 정한다.
"""

import json
import time
import urllib.error
import urllib.request
from uuid import UUID

from django.conf import settings

from accounts.service_signature import SIGNATURE_HEADER, sign_request
from observability.context import outgoing_headers

# 환영 크레딧을 주라고 맡기는 주소. 호스트를 뺀 경로다. 서명에도 이 글자가 들어간다
WELCOME_PATH = '/api/v1/billing/service/grants/welcome'

# 결제 서버의 답을 기다리는 가장 긴 시간(초). 워커가 죽은 서버를 무한정 기다리지 않게 한다
TIMEOUT_SECONDS = 5

# 결제 서버가 돌려주는 결과. 응답의 status 에 이 글자가 온다
GRANTED = 'granted'
ALREADY_GRANTED = 'already_granted'
DISABLED = 'disabled'
WELCOME_OUTCOMES = (GRANTED, ALREADY_GRANTED, DISABLED)


class BillingUnavailableError(Exception):
    """
    결제 서버에 일을 맡기지 못했다. 나중에 다시 맡기면 될 수 있다.

    닿지 못했거나, 시간 안에 답이 없었거나, 알 수 없는 답이 왔거나, 이 서버의 설정이 빠진 경우다.
    글에는 상태 코드나 오류의 종류만 싣는다. 비밀과 서명은 싣지 않는다.
    """


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """다른 주소로 가라는 답을 따라가지 않는다. 서명한 요청이 우리가 고르지 않은 곳으로 가면 안 된다."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def grant_welcome_credit(*, user_public_id: UUID) -> str:
    """
    결제 서버에 이 사용자에게 환영 크레딧을 주라고 맡기고, 결과를 돌려준다.

    결과는 GRANTED(이번에 줬다), ALREADY_GRANTED(전에 이미 받았다), DISABLED(결제 서버가 꺼 두었다) 중 하나다.
    셋 다 "맡길 일이 끝났다"는 뜻이다. 그 밖의 모든 경우는 BillingUnavailableError 다.
    같은 사용자로 여러 번 불러도 크레딧은 한 번만 들어간다. 그것은 결제 서버가 지킨다.
    """
    body = json.dumps({'user_id': str(user_public_id)}).encode()
    status_code, text = _post(WELCOME_PATH, body)
    if status_code not in (200, 201):
        raise BillingUnavailableError(f'결제 서버가 {status_code} 로 답했다')
    return _read_outcome(text)


def _post(path: str, body: bytes) -> tuple[int, bytes]:
    """서명한 POST 를 결제 서버에 보내고 상태 코드와 본문을 돌려준다. 닿지 못하면 BillingUnavailableError 다."""
    request = urllib.request.Request(
        settings.BILLING_URL + path,
        data=body,
        method='POST',
        headers=_headers(path, body),
    )
    try:
        with _opener().open(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        # 4xx 와 5xx 는 예외로 온다. 답은 받은 것이다
        return exc.code, b''
    except OSError as exc:
        # 연결 실패와 시간 초과를 포함한다. 오류의 글에는 주소가 들어 있을 수 있어 종류만 적는다
        raise BillingUnavailableError(f'결제 서버에 닿지 못했다: {type(exc).__name__}') from exc


def _headers(path: str, body: bytes) -> dict[str, str]:
    """요청에 붙일 머리말. 서명과, 추적을 이어 주는 값이다."""
    secret = settings.BILLING_SERVICE_SECRET
    if not secret:
        raise BillingUnavailableError('BILLING_SERVICE_SECRET 이 없다')
    signature = sign_request(secret=secret, method='POST', request_uri=path, body=body, sent_at=int(time.time()))
    return {'Content-Type': 'application/json', SIGNATURE_HEADER: signature, **outgoing_headers()}


def _opener() -> urllib.request.OpenerDirector:
    """
    요청을 보낼 때 쓰는 것. 환경 변수의 프록시를 쓰지 않고, 다른 주소로 가라는 답을 따라가지 않는다.

    우리 서버끼리의 요청이다. 개발자의 PC 에 잡힌 프록시(HTTP_PROXY)를 거쳐 나가면 안 된다.
    """
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _read_outcome(text: bytes) -> str:
    """결제 서버의 답에서 결과를 꺼낸다. 아는 결과가 아니면 BillingUnavailableError 다."""
    try:
        outcome = json.loads(text).get('status')
    except (ValueError, AttributeError) as exc:
        raise BillingUnavailableError('결제 서버의 답을 읽지 못했다') from exc
    if outcome not in WELCOME_OUTCOMES:
        raise BillingUnavailableError('결제 서버가 모르는 결과로 답했다')
    return outcome
