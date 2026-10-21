# auth-server/accounts/billing_client.py

"""
결제 서버를 부른다. 부르는 일은 셋이다.
  - 본인인증을 마친 사용자에게 환영 크레딧을 주라고 맡긴다(welcome_credit.py)
  - 사용자의 결제 자격(성년이 되는 날, 보호자 동의)을 알린다(payment_eligibility.py, #336)
  - 사용자가 탈퇴했다고 알린다(withdrawal.py, #603)

요청마다 서명을 붙인다(service_signature.py). 결제 서버가 그것으로 인증 서버임을 확인한다.

이 모듈은 요청 하나를 보내고 결과를 돌려주는 일만 한다. 언제 부르는지, 실패하면 언제 다시 부르는지는
모른다. 그것은 부르는 모듈이 정한다.
"""

import json
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from uuid import UUID

from django.conf import settings

from accounts.service_signature import SIGNATURE_HEADER, sign_request
from observability.context import outgoing_headers
from observability.http_spans import client_span, mark_unreachable, record_status

# 환영 크레딧을 주라고 맡기는 주소. 호스트를 뺀 경로다. 서명에도 이 글자가 들어간다
WELCOME_PATH = '/api/v1/billing/service/grants/welcome'

# 결제 자격을 알리는 주소(결제 서버의 #337)
ELIGIBILITY_PATH = '/api/v1/billing/service/eligibility'

# 탈퇴를 알리는 주소(#603, docs/architecture/withdrawal.md). {user_id} 에 공개 ID 가 들어간다
WITHDRAWAL_PATH = '/api/v1/billing/service/users/{user_id}/withdrawal'

# 결제 서버의 답을 기다리는 가장 긴 시간(초). 워커가 죽은 서버를 무한정 기다리지 않게 한다
TIMEOUT_SECONDS = 5

# 결제 서버가 돌려주는 결과. 응답의 status 에 이 글자가 온다
GRANTED = 'granted'
ALREADY_GRANTED = 'already_granted'
DISABLED = 'disabled'
WELCOME_OUTCOMES = (GRANTED, ALREADY_GRANTED, DISABLED)

# 결제 자격에 결제 서버가 돌려주는 결과. 둘 다 "알릴 일이 끝났다"는 뜻이다
APPLIED = 'applied'
# 결제 서버가 이미 같거나 더 높은 버전을 가지고 있다
STALE = 'stale'
ELIGIBILITY_OUTCOMES = (APPLIED, STALE)

# 탈퇴에 결제 서버가 돌려주는 결과. 정리했다(이미 정리했거나 그 사용자의 것이 없던 것도 같다)
PROCESSED = 'processed'
WITHDRAWAL_OUTCOMES = (PROCESSED,)


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
    return _read_outcome(text, WELCOME_OUTCOMES)


def report_payment_eligibility(
    *, user_public_id: UUID, version: int, legal_adult_from: date | None, guardian_consent: bool
) -> str:
    """
    결제 서버에 사용자의 결제 자격을 알리고, 결과를 돌려준다.

    결과는 APPLIED(받아 적었다)나 STALE(이미 같거나 더 높은 버전이 있다)다. 둘 다 끝난 것이다.
    그 밖의 모든 경우(결제 서버가 이 주소를 모르는 옛 판이라 404 인 것을 포함한다)는 BillingUnavailableError 다.
    legal_adult_from 이 None 이면 이미 성년이다. 날짜는 한국 날짜다.
    """
    body = json.dumps(
        {
            'user_id': str(user_public_id),
            'version': version,
            'legal_adult_from': legal_adult_from.isoformat() if legal_adult_from else None,
            'guardian_consent': guardian_consent,
        }
    ).encode()
    status_code, text = _post(ELIGIBILITY_PATH, body)
    if status_code != 200:
        raise BillingUnavailableError(f'결제 서버가 {status_code} 로 답했다')
    return _read_outcome(text, ELIGIBILITY_OUTCOMES)


def report_withdrawal(*, user_public_id: UUID, withdrawn_at: datetime) -> str:
    """
    결제 서버에 사용자가 탈퇴했다고 알리고, 결과를 돌려준다.

    결과는 PROCESSED 다. 결제 서버가 그 사용자의 홀드를 돌려주고 크레딧을 소멸로 적고 결제 자격을 지웠다는 뜻이다.
    같은 사용자로 여러 번 불러도 결과가 같다. 그것은 결제 서버가 지킨다.
    그 밖의 모든 경우(결제 서버가 이 주소를 모르는 옛 판이라 404 인 것을 포함한다)는 BillingUnavailableError 다.
    """
    path = WITHDRAWAL_PATH.format(user_id=user_public_id)
    body = json.dumps({'withdrawn_at': withdrawn_at.isoformat()}).encode()
    status_code, text = _post(path, body)
    if status_code != 200:
        raise BillingUnavailableError(f'결제 서버가 {status_code} 로 답했다')
    return _read_outcome(text, WITHDRAWAL_OUTCOMES)


def _post(path: str, body: bytes) -> tuple[int, bytes]:
    """
    서명한 POST 를 결제 서버에 보내고 상태 코드와 본문을 돌려준다. 닿지 못하면 BillingUnavailableError 다.

    작업 안에서 부르면 client span 을 건다(observability/http_spans.py). 머리말을 그 안에서 만들어
    traceparent 가 그 span 을 부모로 가리킨다. 결제 서버의 span 이 그 아래에 붙는다.
    """
    url = settings.BILLING_URL + path
    with client_span('POST', url) as span:
        request = urllib.request.Request(url, data=body, method='POST', headers=_headers(path, body))
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
            raise BillingUnavailableError(f'결제 서버에 닿지 못했다: {type(exc).__name__}') from exc


def _headers(path: str, body: bytes) -> dict[str, str]:
    """요청에 붙일 머리말. 서명과, 추적을 이어 주는 값이다."""
    secret = settings.BILLING_SECRET
    if not secret:
        raise BillingUnavailableError('BILLING_SECRET 이 없다')
    signature = sign_request(secret=secret, method='POST', request_uri=path, body=body, sent_at=int(time.time()))
    return {'Content-Type': 'application/json', SIGNATURE_HEADER: signature, **outgoing_headers()}


def _opener() -> urllib.request.OpenerDirector:
    """
    요청을 보낼 때 쓰는 것. 환경 변수의 프록시를 쓰지 않고, 다른 주소로 가라는 답을 따라가지 않는다.

    우리 서버끼리의 요청이다. 개발자의 PC 에 잡힌 프록시(HTTP_PROXY)를 거쳐 나가면 안 된다.
    """
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _read_outcome(text: bytes, known: tuple[str, ...]) -> str:
    """결제 서버의 답에서 결과를 꺼낸다. known 에 없는 결과면 BillingUnavailableError 다."""
    try:
        outcome = json.loads(text).get('status')
    except (ValueError, AttributeError) as exc:
        raise BillingUnavailableError('결제 서버의 답을 읽지 못했다') from exc
    if outcome not in known:
        raise BillingUnavailableError('결제 서버가 모르는 결과로 답했다')
    return outcome
