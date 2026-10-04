# game-server/app/tables/passwords.py

"""
테이블의 비밀번호를 저장할 모양으로 바꾸고, 맞는지 확인한다.

비밀번호를 그대로 저장하지 않는다. 테이블의 비밀번호는 여럿이 나눠 쓰는 가벼운 것이지만,
사람들은 다른 곳에서 쓰는 비밀번호를 여기에도 적는다. DB 가 새어 나가도 원래 글자를 알 수 없어야 한다.

scrypt 를 쓴다. 일부러 느리고 메모리를 많이 쓰는 방식이라, 새어 나간 값을 대입해 보는 데 돈이 많이 든다.
파이썬에 들어 있어서(hashlib) 패키지를 더하지 않는다.

여기의 함수는 계산만 한다. 한 번에 0.2 초쯤 걸리므로, 부르는 쪽이 다른 요청을 막지 않게 따로 돌려야 한다(service.py).
"""

import base64
import hashlib
import hmac
import secrets

# scrypt 의 비용. N 은 반복과 메모리(2 의 거듭제곱), R 은 블록 크기, P 는 병렬 횟수다.
# 메모리는 약 128 * N * R 바이트(여기서는 16MB)를 쓴다. 값을 올리면 대입이 더 비싸지고 서버도 더 느려진다
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 5
# 만들어 내는 값의 길이(바이트)
KEY_LENGTH = 32
# 소금의 길이(바이트). 비밀번호마다 새로 만든다
SALT_LENGTH = 16
# 저장하는 글의 맨 앞에 붙이는 이름. 나중에 방식을 바꿔도 옛 값이 어느 방식인지 알 수 있다
SCHEME = 'scrypt'


def derive_key(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    """비밀번호와 소금에서 값을 계산한다. 같은 입력이면 늘 같은 값이 나온다."""
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=KEY_LENGTH)


def encode(data: bytes) -> str:
    """바이트를 저장할 수 있는 글자로 바꾼다."""
    return base64.b64encode(data).decode()


def hash_password(password: str) -> str:
    """
    비밀번호를 저장할 모양으로 바꾼다. 결과는 "scrypt$N$R$P$소금$값" 이다.

    소금은 비밀번호마다 새로 만드는 무작위 값이다. 같은 비밀번호를 쓰는 테이블 둘의 저장된 값이 달라진다.
    미리 계산해 둔 표로 한꺼번에 푸는 일을 막는다.
    비용(N, R, P)을 함께 적어 둔다. 나중에 비용을 올려도 옛 값을 그때의 비용으로 확인할 수 있다.
    """
    salt = secrets.token_bytes(SALT_LENGTH)
    key = derive_key(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f'{SCHEME}${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${encode(salt)}${encode(key)}'


def verify_password(password: str, stored: str) -> bool:
    """
    비밀번호가 저장된 것과 맞는지 확인한다.

    저장된 값에 적힌 소금과 비용으로 다시 계산해서 비교한다.
    compare_digest: 어디서 달라졌는지에 따라 걸리는 시간이 달라지지 않게 비교한다.
    보통의 == 는 처음 다른 글자에서 멈춰서, 걸린 시간으로 앞에서 몇 글자가 맞았는지 새어 나간다.
    """
    scheme, n, r, p, salt, key = stored.split('$')
    if scheme != SCHEME:
        return False
    expected = base64.b64decode(key)
    actual = derive_key(password, base64.b64decode(salt), int(n), int(r), int(p))
    return hmac.compare_digest(actual, expected)
