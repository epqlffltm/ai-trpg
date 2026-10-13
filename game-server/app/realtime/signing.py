# game-server/app/realtime/signing.py

"""
실시간 신호의 서명(#75). 보낼 때 붙이고, 받을 때 맞춰 본다.

신호는 PostgreSQL 의 NOTIFY 로 오간다(app/realtime/signals.py). NOTIFY 에는 권한 검사가 없다.
같은 데이터베이스에 접속한 계정이면 누구나 어느 채널로든 보낼 수 있다. 게시판과 결제 서버의 계정도 같은 DB 에 붙는다.
그래서 게임 서버만 아는 비밀(SIGNAL_SECRET)로 신호마다 서명한다. 서명이 맞지 않는 신호는 버린다.

막는 것: 꾸며 낸 신호. 남의 이름으로 "입력 중"을 띄우거나, 쓰이지 않은 서술을 미리 보기로 보내는 것.
막지 않는 것:
  - 엿듣기. LISTEN 에도 권한 검사가 없다. 실리는 것은 그 테이블 사람들이 원래 보는 것(입력 중인 사람, 서술의 글)이다.
  - 다시 보내기. 엿들은 신호를 그대로 다시 보내면 서명이 맞는다. 저장된 것의 신호는 DB 를 다시 읽게 할 뿐이고,
    입력 중과 서술의 조각은 그 테이블이 이미 본 것을 한 번 더 보일 뿐이다. 시각이나 번호를 붙여 막을 만큼의 일이 아니다.

서명은 'HMAC-SHA256 의 16진수 64자:신호' 의 모양이다. 앞에 붙는 것은 65 바이트다.
가장 긴 신호(서술의 조각, 6080 바이트 안쪽)에 붙여도 NOTIFY 의 상한(8000 바이트)보다 짧다.
"""

import hashlib
import hmac
import logging
import secrets

from app.core.config import Settings

logger = logging.getLogger(__name__)

# 서명이 맞지 않는 신호를 버렸을 때의 오류 코드. 규격은 docs/observability.md 에 있다
BAD_SIGNATURE_ERROR_CODE = 'signals.bad_signature'

# 서명과 신호 사이의 구분. 서명은 16진수라 이 글자가 없다
SEPARATOR = ':'

# 비밀을 적지 않았을 때 만드는 키의 길이(바이트)
RANDOM_KEY_BYTES = 32


class SignalSigner:
    """한 비밀로 신호에 서명하고, 받은 신호의 서명을 맞춰 본다."""

    def __init__(self, key: bytes) -> None:
        self._key = key

    def signature(self, payload: str) -> str:
        """신호의 서명. 16진수 64자다."""
        return hmac.new(self._key, payload.encode(), hashlib.sha256).hexdigest()

    def sign(self, payload: str) -> str:
        """신호 앞에 서명을 붙인다. 채널에는 이것을 보낸다."""
        return f'{self.signature(payload)}{SEPARATOR}{payload}'

    def verify(self, signed: str) -> str | None:
        """
        받은 글자의 서명을 맞춰 보고 신호를 돌려준다. 서명이 없거나 맞지 않으면 None.

        compare_digest: 앞에서부터 몇 글자가 맞았는지가 걸린 시간으로 새지 않게 비교한다.
        바이트로 바꿔 비교한다. 글자로 넘기면 ASCII 가 아닌 글자(꾸민 쪽이 마음대로 넣는다)에서 예외가 난다.
        """
        signature, _, payload = signed.partition(SEPARATOR)
        if not hmac.compare_digest(signature.encode(), self.signature(payload).encode()):
            return None
        return payload


def signer_from(settings: Settings) -> SignalSigner:
    """
    설정의 비밀로 서명하는 것을 만든다. 서버가 뜰 때 한 번 부른다.

    비밀이 없으면 무작위로 만들고 경고를 남긴다. 서버가 하나면 그대로 된다.
    여럿이면 서로의 신호를 버리므로 SIGNAL_SECRET 을 같은 값으로 적어야 한다.
    """
    key = settings.signal_key()
    if key is None:
        logger.warning('SIGNAL_SECRET 이 없어 무작위로 만들었다. 서버를 여럿 띄우면 같은 값을 적어야 한다')
        key = secrets.token_bytes(RANDOM_KEY_BYTES)
    return SignalSigner(key)
