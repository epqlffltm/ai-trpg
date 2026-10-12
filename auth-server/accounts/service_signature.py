# auth-server/accounts/service_signature.py

"""
우리 서버끼리 부르는 요청에 붙이는 서명을 만든다.

결제 서버는 사용자의 토큰이 아니라 이 서명을 보고 "인증 서버가 보낸 요청"임을 안다.
두 서버만 아는 비밀로 요청의 메서드, 주소, 본문, 보낸 시각을 서명한다(HMAC-SHA256).

    X-Service-Signature: t=<보낸 시각(초)>,v1=<서명>

서명하는 글자는 "<보낸 시각>.<메서드>\\n<주소>\\n<본문>" 이다. 주소는 호스트를 뺀 경로다.
받는 쪽의 규칙은 billing-server/internal/serviceauth 에 있다. 두 쪽의 테스트에 같은 값이 적혀 있다.

비밀을 머리말에 그대로 싣지 않는다. 그러면 비밀이 요청마다 오가고, 로그나 프록시에 한 번 찍히면 끝이다.
서명은 그 요청에만 쓸 수 있고, 결제 서버는 5분이 지난 것을 받지 않는다.
"""

import hashlib
import hmac

# 서명을 싣는 머리말의 이름
SIGNATURE_HEADER = 'X-Service-Signature'


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
