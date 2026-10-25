# board-server/contract/harness/signing.py

"""
인증 서버가 서버끼리의 요청에 하는 서명(auth-server/accounts/service_signature.py 와 같은 모양).

머리말 X-Service-Signature: t=<보낸 시각>,v1=<hex>
v1 = HMAC-SHA256(비밀, "<시각>.<메서드>\\n<경로>\\n" + 본문)
"""

import hashlib
import hmac
import time

SIGNATURE_HEADER = 'X-Service-Signature'


def sign(secret: str, method: str, path: str, body: bytes, sent_at: int | None = None) -> str:
    """요청 하나에 서명한 머리말의 값."""
    moment = int(time.time()) if sent_at is None else sent_at
    message = f'{moment}.{method.upper()}\n{path}\n'.encode() + body
    digest = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return f't={moment},v1={digest}'
