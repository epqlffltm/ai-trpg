# auth-server/accounts/service_signature.py

"""
우리 서버끼리 부르는 요청에 붙이는 서명을 만들고 확인한다.

결제 서버는 사용자의 토큰이 아니라 이 서명을 보고 "인증 서버가 보낸 요청"임을 안다.
두 서버만 아는 비밀로 요청의 메서드, 주소, 본문, 보낸 시각을 서명한다(HMAC-SHA256).
반대로 이 서버도 결제 서버가 보낸 보호자 알림(#352)을 이 서명으로 확인한다(verify_request).
비밀은 같은 짝이다(BILLING_SECRET).
서명에 주소가 들어가므로 한쪽 방향의 요청을 다른 방향의 주소에 다시 쓸 수 없다.

    X-Service-Signature: t=<보낸 시각(초)>,v1=<서명>

서명하는 글자는 "<보낸 시각>.<메서드>\\n<주소>\\n<본문>" 이다. 주소는 호스트를 뺀 경로다.
받는 쪽의 규칙은 billing-server/internal/serviceauth 에 있다. 두 쪽의 테스트에 같은 값이 적혀 있다.

비밀을 머리말에 그대로 싣지 않는다. 그러면 비밀이 요청마다 오가고, 로그나 프록시에 한 번 찍히면 끝이다.
서명은 그 요청에만 쓸 수 있고, 받는 쪽은 앞뒤로 5분이 넘게 벌어진 것을 받지 않는다.
"""

import hashlib
import hmac
import re

# 서명을 싣는 머리말의 이름
SIGNATURE_HEADER = 'X-Service-Signature'

# 서명의 시각이 지금과 벌어져도 되는 가장 긴 시간(초). 앞뒤로 같다. 결제 서버(internal/signature)와 같은 값이다
TOLERANCE_SECONDS = 5 * 60
# 서명에 쓰는 비밀의 가장 짧은 길이. 비밀이 비었거나 짧으면 누구나 서명을 만들 수 있다
MIN_SECRET_LENGTH = 32
# 머리말의 모양: t=<초>,v1=<16진수 64자>
_HEADER = re.compile(r't=(?P<sent_at>-?\d{1,19}),v1=(?P<digest>[0-9a-f]{64})')


def sign_request(*, secret: str, method: str, request_uri: str, body: bytes, sent_at: int) -> str:
    """
    요청에 서명해 머리말에 실을 글자를 만든다.

    request_uri 는 주소의 경로와 그 뒤에 붙은 값이다(/api/v1/billing/service/grants/welcome). 호스트는 넣지 않는다.
    body 는 보내는 바이트 그대로다. 서명한 뒤에 본문을 다시 만들면 빈칸 하나로도 서명이 어긋난다.
    sent_at 은 보낸 시각(유닉스 시각, 초)이다.
    """
    payload = f'{sent_at}.{method}\n{request_uri}\n'.encode() + body
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f't={sent_at},v1={digest}'


def verify_request(*, secret: str, header: str, method: str, request_uri: str, body: bytes, now: int) -> bool:
    """
    머리말의 서명이 이 요청(메서드, 주소, 본문)의 것이고 방금 보낸 것인지 본다. 맞으면 True 다.

    이유를 나누지 않는다. 무엇이 틀렸는지 알려 주면 서명을 꾸며 내는 쪽에 도움이 된다.
    두 서명을 견줄 때는 걸리는 시간이 어디서 틀렸는지에 따라 달라지지 않게 한다(compare_digest).
    """
    if len(secret) < MIN_SECRET_LENGTH:
        return False
    matched = _HEADER.fullmatch(header or '')
    if matched is None:
        return False
    sent_at = int(matched['sent_at'])
    expected = sign_request(secret=secret, method=method, request_uri=request_uri, body=body, sent_at=sent_at)
    if not hmac.compare_digest(expected, header):
        return False
    return abs(now - sent_at) <= TOLERANCE_SECONDS
