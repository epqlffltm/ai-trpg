# auth-server/accounts/mail_crypto.py

"""
발송함에 적는 메일 본문을 암호화하고, 워커가 꺼낼 때 복호화한다.

메일 본문에는 인증 코드와 비밀번호 재설정 토큰이 원문으로 들어 있다.
인증 코드는 해시로만 저장하는데(email_codes.py), 발송함에 본문이 그대로 놓이면
DB 를 읽을 수 있는 사람이 보내기 전의 코드와 토큰을 얻는다.
암호화해 두면 DB 만으로는 읽을 수 없다. 서버의 비밀키가 함께 있어야 한다.

해시가 아니라 암호화인 이유: 워커가 원래 본문을 메일로 보내야 한다. 되돌릴 수 있어야 한다.
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from django.utils.crypto import salted_hmac

# 암호화 키를 만들 때 SECRET_KEY 에 섞는 값.
# 같은 SECRET_KEY 에서 나온 다른 용도의 키(인증 코드 해시, 로그인 티켓)와 겹치지 않게 한다
KEY_SALT = 'accounts.mail_crypto.outbox_body'


class UnreadableMailBodyError(Exception):
    """
    본문을 복호화할 수 없다.

    암호화한 뒤에 SECRET_KEY 가 바뀌었거나, DB 의 값이 손상되었거나 누군가 고친 경우다.
    """


def encrypt_mail_body(body: str) -> str:
    """메일 본문을 암호화해 DB 에 넣을 문자열로 돌려준다."""
    return _fernet().encrypt(body.encode()).decode()


def decrypt_mail_body(encrypted_body: str) -> str:
    """
    암호화된 본문을 원래 본문으로 되돌린다. 되돌릴 수 없으면 UnreadableMailBodyError 를 낸다.

    Fernet 은 암호문이 고쳐졌는지도 확인한다. DB 의 값을 누가 바꿨다면 여기서 걸린다.
    """
    try:
        return _fernet().decrypt(encrypted_body.encode()).decode()
    except InvalidToken as exc:
        raise UnreadableMailBodyError from exc


def _fernet() -> Fernet:
    """
    SECRET_KEY 에서 암호화 키를 만들어 Fernet 을 돌려준다.

    키를 따로 저장하지 않는다. SECRET_KEY 는 DB 가 아니라 서버의 환경 변수에 있으므로,
    DB 만 얻은 사람은 이 키를 만들 수 없다.
    Fernet 의 키는 32바이트를 base64 로 적은 것이다. SHA-256 의 결과가 32바이트다.
    """
    key = salted_hmac(KEY_SALT, 'key', algorithm='sha256').digest()
    return Fernet(base64.urlsafe_b64encode(key))
