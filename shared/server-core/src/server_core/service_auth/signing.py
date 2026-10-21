# shared/server-core/src/server_core/service_auth/signing.py

"""
우리 서버끼리 부르는 요청이 정말 그 서버가 보낸 것인지 확인한다(서명, HMAC-SHA256).

알림을 넣는 서버(게임, 결제, 게시판)는 사용자의 토큰을 싣지 않는다.
사용자가 없는 자리(정리 작업, 라운드를 닫는 작업)에서도 알림을 넣어야 하고,
사용자의 토큰으로 알림을 넣을 수 있으면 사용자가 남에게 가짜 알림을 넣을 수 있다.
그 대신 두 서버만 아는 비밀로 요청(메서드, 주소, 본문)에 서명해 머리말에 싣는다.

모양은 결제 서버의 것(billing-server/internal/serviceauth)과 같다. 넣는 서버가 서명하는 코드를 하나로 쓸 수 있다.

    X-Service-Signature: t=<보낸 시각(초)>,v1=<HMAC-SHA256(비밀, "<시각>.<메서드>\\n<주소>\\n<본문>") 의 16진수>

  - 주소까지 서명한다. 한 서버의 서명을 가로채 다른 주소(다른 서버의 자리)에 붙여 쓸 수 없다
  - 시각을 함께 서명한다. 앞뒤 5분(TOLERANCE_SECONDS)을 넘긴 서명은 받지 않는다. 가로챈 요청을 나중에 다시 보낼 수 없다
  - 비밀을 머리말에 그대로 싣지 않는다. 그러면 비밀이 요청마다 오가고, 로그나 프록시에 한 번 찍히면 끝이다
"""

import hashlib
import hmac

# 서명을 싣는 머리말
SIGNATURE_HEADER = 'X-Service-Signature'
# 서명의 시각이 지금과 벌어져도 되는 가장 긴 시간(초). 앞뒤로 같다. 서버끼리의 시계 차이를 봐준다
TOLERANCE_SECONDS = 5 * 60
# 서명에 쓰는 비밀의 가장 짧은 길이. 결제 서버와 같다
MIN_SECRET_LENGTH = 32


def signed_content(sent_at: str, method: str, path: str, body: bytes) -> bytes:
    """서명하는 글자. 보낸 시각과 요청이다. 메서드와 주소에는 줄바꿈이 없어서 세 부분이 섞이지 않는다."""
    return f'{sent_at}.{method}\n{path}\n'.encode() + body


def digest(secret: str, sent_at: str, method: str, path: str, body: bytes) -> str:
    """서명 값(16진수)."""
    return hmac.new(secret.encode(), signed_content(sent_at, method, path, body), hashlib.sha256).hexdigest()


def sign(secret: str, sent_at: int, method: str, path: str, body: bytes) -> str:
    """요청에 서명해 머리말에 실을 글자를 만든다. 넣는 서버(와 테스트)가 하는 일이다."""
    return f't={sent_at},v1={digest(secret, str(sent_at), method, path, body)}'


def split_header(header: str) -> tuple[str, str] | None:
    """'t=<시각>,v1=<서명>' 을 시각과 서명으로 나눈다. 그 모양이 아니면 None 이다."""
    time_part, comma, signature_part = header.partition(',')
    if not comma or not time_part.startswith('t=') or not signature_part.startswith('v1='):
        return None
    return time_part.removeprefix('t='), signature_part.removeprefix('v1=')


def is_fresh(sent_at: str, now: float) -> bool:
    """서명의 시각이 지금에서 앞뒤 TOLERANCE_SECONDS 안쪽인가. 숫자가 아니면 아니다."""
    if not sent_at.isascii() or not sent_at.isdigit():
        return False
    return abs(now - int(sent_at)) <= TOLERANCE_SECONDS


def is_valid(secret: str, header: str | None, method: str, path: str, body: bytes, now: float) -> bool:
    """
    머리말의 서명이 이 요청(메서드, 주소, 본문)의 것이고 방금 만든 것인가.

    이유를 나누지 않고 참/거짓만 답한다. 무엇이 틀렸는지 알려 주면 서명을 꾸며 내는 쪽에 도움이 된다.
    비밀이 비었거나 짧으면 누구나 서명을 만들 수 있다. 그런 비밀로는 하나도 받지 않는다.
    """
    if len(secret) < MIN_SECRET_LENGTH or header is None:
        return False
    parts = split_header(header)
    if parts is None:
        return False
    sent_at, signature = parts
    # 두 서명을 견줄 때 걸리는 시간이 어디서 틀렸는지에 따라 달라지지 않게 한다
    if not hmac.compare_digest(signature.encode(), digest(secret, sent_at, method, path, body).encode()):
        return False
    return is_fresh(sent_at, now)
