# trpg-server/app/billing/signing.py

"""
결제 서버에 보내는 요청에 서명한다.

게임 서버는 사용자의 토큰을 싣지 않는다. 사용자가 없는 자리(라운드를 닫는 작업, 정리 작업)에서도 부르고,
사용자의 토큰으로 "이 사용자의 크레딧을 빼라"를 할 수 있으면 사용자가 직접 그 주소를 부를 수 있다.
그 대신 두 서버만 아는 비밀로 요청(메서드, 주소, 본문)에 서명해 머리말에 싣는다.

모양은 결제 서버가 정했다(billing-server/internal/serviceauth). 바꾸면 두 서버를 함께 바꾼다.

    X-Service-Signature: t=<보낸 시각(초)>,v1=<HMAC-SHA256(비밀, "<시각>.<메서드>\\n<주소>\\n<본문>") 의 16진수>

본문은 보내는 바이트 그대로에 서명한다. JSON 을 한 번 만들어 서명하고 그것을 보낸다. 다시 만들면 빈칸 하나로도 어긋난다.
"""

import hashlib
import hmac

# 서명을 싣는 머리말
SIGNATURE_HEADER = 'X-Service-Signature'


def signed_content(sent_at: int | str, method: str, path: str, body: bytes) -> bytes:
    """
    서명하는 글자. 보낸 시각과 요청이다. 메서드와 주소에는 줄바꿈이 없어서 세 부분이 섞이지 않는다.

    받는 쪽(app/core/service_auth.py)은 머리말에서 읽은 시각의 글자를 그대로 넣는다.
    """
    return f'{sent_at}.{method}\n{path}\n'.encode() + body


def sign(secret: str, sent_at: int, method: str, path: str, body: bytes) -> str:
    """요청에 서명해 머리말에 실을 글자를 만든다. path 는 호스트를 뺀 경로다(/api/v1/billing/service/holds)."""
    digest = hmac.new(secret.encode(), signed_content(sent_at, method, path, body), hashlib.sha256).hexdigest()
    return f't={sent_at},v1={digest}'
