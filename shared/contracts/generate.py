# shared/contracts/generate.py

"""
공통 규격의 시험 파일 가운데 계산해서 만드는 둘을 다시 만든다(#786). 서버의 코드를 쓰지 않는다.

  - service-signature.json: 서버끼리의 서명(X-Service-Signature). HMAC-SHA256 을 표준 라이브러리로 직접 계산한다.
    서버의 서명 코드가 이 값과 같아야 한다. 서버의 코드로 기대값을 만들면 틀린 코드가 스스로를 맞다고 하게 된다.
  - access-tokens.json: 인증 서버의 access 토큰을 받는 쪽의 검증. 돌릴 때마다 새 RSA 키를 만들어 서명하고,
    공개키(JWKS)와 토큰만 적는다. 개인키는 적지 않는다(저장소에 남지 않는다). 그래서 토큰을 고치려면 모두 다시 만든다.

redaction.json(로그 가리기)은 손으로 적는다. 기대값이 계산이 아니라 정한 규칙이다.

    cd shared/server-core; uv run python ../contracts/generate.py

같은 입력이면 서명의 파일은 같게 나온다. 토큰의 파일은 키가 바뀌어 늘 달라진다. 규칙이 바뀔 때만 다시 만든다.
"""

import base64
import hashlib
import hmac
import json
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

HERE = Path(__file__).parent

# 서명의 비밀. 32자(가장 짧은 길이) 이상이다. 시험에만 쓴다
SECRET = 'contract-only-secret-0123456789-abcdef'
# 시험의 지금 시각(유닉스 초). 받는 쪽은 앞뒤 5분까지 받는다
NOW = 1_800_000_000
TOLERANCE = 300

# 토큰의 발급자와 이 서버의 대상, 키의 ID
ISSUER = 'ai-trpg-auth'
AUDIENCE = 'ai-trpg-contract'
KID = 'contract-key'
USER_ID = '11111111-2222-4333-8444-555555555555'
# 만료가 먼 미래(2100-01-01)와 지난 과거(2020-01-01). 받는 쪽은 진짜 지금 시각으로 만료를 본다
FAR_FUTURE = 4_102_444_800
PAST = 1_577_836_800


def digest(secret: str, timestamp: str, method: str, path: str, body: bytes) -> str:
    """ "<시각>.<메서드>\\n<주소>\\n<본문>" 의 HMAC-SHA256(16진수 소문자)."""
    content = f'{timestamp}.{method}\n{path}\n'.encode() + body
    return hmac.new(secret.encode(), content, hashlib.sha256).hexdigest()


def header(secret: str, timestamp: str, method: str, path: str, body: bytes) -> str:
    return f't={timestamp},v1={digest(secret, timestamp, method, path, body)}'


def request(method: str, path: str, body: str) -> dict:
    return {'method': method, 'path': path, 'body': body}


def signing_cases() -> dict:
    """서명 만들기와 확인의 경우들. 본문은 UTF-8 글자로 적는다."""
    post = request('POST', '/api/v1/billing/service/holds', '{"user_id":"u1","amount":"12.5"}')
    get = request('GET', '/api/v1/billing/service/wallets/u1?limit=20', '')
    korean = request('POST', '/api/v1/notifications/service/notices', '{"title":"새 알림 🎲"}')
    body = post['body'].encode()

    def sign(case: dict, timestamp: int) -> str:
        return header(SECRET, str(timestamp), case['method'], case['path'], case['body'].encode())

    good = sign(post, NOW)
    upper = f't={NOW},v1={digest(SECRET, str(NOW), post["method"], post["path"], body).upper()}'
    zero = f'0{NOW}'
    plus = f'+{NOW}'
    verify = [
        ('맞는 서명', post, good, True),
        ('5분 전에 만든 서명', post, sign(post, NOW - TOLERANCE), True),
        ('5분 뒤의 서명(시계가 빠른 서버)', post, sign(post, NOW + TOLERANCE), True),
        ('5분 1초 전에 만든 서명', post, sign(post, NOW - TOLERANCE - 1), False),
        ('5분 1초 뒤의 서명', post, sign(post, NOW + TOLERANCE + 1), False),
        ('다른 비밀로 만든 서명', post, header(SECRET + 'x', str(NOW), post['method'], post['path'], body), False),
        ('다른 주소의 서명', {**post, 'path': '/api/v1/billing/service/grants'}, good, False),
        ('다른 메서드의 서명', {**post, 'method': 'PUT'}, good, False),
        ('본문이 바뀐 요청', {**post, 'body': post['body'] + ' '}, good, False),
        ('서명이 대문자 16진수', post, upper, False),
        ('시각 앞에 0', post, header(SECRET, zero, post['method'], post['path'], body), False),
        ('시각 앞에 0(서명은 0 이 없는 시각으로)', post, f't={zero},v1={good.split(",v1=")[1]}', False),
        ('시각 앞에 +', post, header(SECRET, plus, post['method'], post['path'], body), False),
        ('음수의 시각', post, header(SECRET, '-1', post['method'], post['path'], body), False),
        ('칸의 차례가 뒤바뀜', post, f'v1={good.split(",v1=")[1]},t={NOW}', False),
        ('쉼표 뒤의 빈칸', post, good.replace(',', ', '), False),
        ('뒤에 다른 칸', post, good + ',v2=00', False),
        ('v1 이 없음', post, f't={NOW}', False),
        ('빈 머리말', post, '', False),
        ('머리말이 없음', post, None, False),
    ]
    short = SECRET[:31]
    return {
        'secret': SECRET,
        'now': NOW,
        'sign': [
            {'name': '본문이 있는 POST', **post, 'sent_at': NOW, 'header': good},
            {'name': '본문이 빈 GET(주소에 물음표 뒤의 값)', **get, 'sent_at': NOW, 'header': sign(get, NOW)},
            {'name': '한글과 그림 글자가 든 본문', **korean, 'sent_at': NOW, 'header': sign(korean, NOW)},
        ],
        'verify': [{'name': name, **case, 'header': value, 'valid': valid} for name, case, value, valid in verify]
        + [
            {
                'name': '짧은 비밀(31자)로는 맞는 서명도 받지 않는다',
                **post,
                'secret': short,
                'header': header(short, str(NOW), post['method'], post['path'], body),
                'valid': False,
            }
        ],
    }


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def hand_made(header_fields: dict, claims: dict, hmac_key: bytes | None = None) -> str:
    """
    손으로 만든 토큰. 라이브러리가 만들어 주지 않는 것이다.

    hmac_key 가 없으면 서명이 빈 토큰(none), 있으면 그 바이트를 비밀로 쓴 HS256 이다.
    """
    signing_input = f'{b64url(json.dumps(header_fields).encode())}.{b64url(json.dumps(claims).encode())}'
    signature = b'' if hmac_key is None else hmac.new(hmac_key, signing_input.encode(), hashlib.sha256).digest()
    return f'{signing_input}.{b64url(signature)}'


def token_cases() -> dict:
    """access 토큰의 경우들. 받으면 사용자와, 읽는 쪽이면 성인용과 운영자를 적는다."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({'kid': KID, 'use': 'sig', 'alg': 'RS256'})
    base = {
        'sub': USER_ID,
        'iss': ISSUER,
        'aud': ['ai-trpg-auth', AUDIENCE],
        'exp': FAR_FUTURE,
        'iat': PAST,
        'token_type': 'access',
        'ver': 0,
    }

    def signed(claims: dict, *, with_key=key, kid: str | None = KID, drop: tuple[str, ...] = ()) -> str:
        body = {name: value for name, value in {**base, **claims}.items() if name not in drop}
        headers = {'kid': kid} if kid is not None else {}
        return jwt.encode(body, with_key, algorithm='RS256', headers=headers)

    # 공격하는 쪽이 아는 공개키(PEM). 이것을 HS256 의 비밀로 쓰면, 방식을 믿는 검증기는 받아 버린다
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    accepted = [
        ('보통의 access 토큰', signed({}), {'adult_content': False, 'is_operator': False}),
        ('대상이 글자 하나', signed({'aud': AUDIENCE}), {}),
        ('성인용을 볼 수 있다(JSON 의 true)', signed({'adult_content': True}), {'adult_content': True}),
        ('성인용이 글자 "true" 면 볼 수 없다', signed({'adult_content': 'true'}), {'adult_content': False}),
        ('운영자(역할의 목록에 operator)', signed({'roles': ['operator', 'unknown']}), {'is_operator': True}),
        ('역할이 목록이 아니면 운영자가 아니다', signed({'roles': 'operator'}), {'is_operator': False}),
        ('세션 버전이 없으면 0', signed({}, drop=('ver',)), {}),
    ]
    rejected = [
        ('만료됨', signed({'exp': PAST})),
        ('만료가 없음', signed({}, drop=('exp',))),
        ('다른 발급자', signed({'iss': 'someone-else'})),
        ('발급자가 없음', signed({}, drop=('iss',))),
        ('이 서버가 대상에 없음', signed({'aud': ['ai-trpg-auth']})),
        ('refresh 토큰', signed({'token_type': 'refresh'})),
        ('종류가 없음', signed({}, drop=('token_type',))),
        ('사용자가 없음', signed({}, drop=('sub',))),
        ('사용자가 UUID 가 아님', signed({'sub': 'not-a-uuid'})),
        ('세션 버전이 음수', signed({'ver': -1})),
        ('세션 버전이 글자', signed({'ver': '1'})),
        ('발급 시각이 미래(2100년)', signed({'iat': FAR_FUTURE})),
        ('아직 쓸 수 없음(nbf 가 미래)', signed({'nbf': FAR_FUTURE})),
        ('다른 키로 서명', signed({}, with_key=other)),
        ('키 ID 가 없음', signed({}, kid=None)),
        ('모르는 키 ID', signed({}, kid='unknown-key')),
        ('서명 방식 none', hand_made({'alg': 'none', 'typ': 'JWT', 'kid': KID}, base)),
        ('공개키를 비밀로 쓴 HS256', hand_made({'alg': 'HS256', 'typ': 'JWT', 'kid': KID}, base, public_pem)),
        ('서명이 잘린 토큰', signed({})[:-10]),
        ('토큰의 모양이 아님', 'not.a.token'),
    ]
    return {
        'issuer': ISSUER,
        'audience': AUDIENCE,
        'user_id': USER_ID,
        'jwks': {'keys': [jwk]},
        'accepted': [{'name': name, 'token': token, **claims} for name, token, claims in accepted],
        'rejected': [{'name': name, 'token': token} for name, token in rejected],
    }


# 파일의 머리에 적는 알림
NOTE = 'shared/contracts/generate.py 가 만든다. 손으로 고치지 않는다. 규칙은 shared/contracts/README.md'


def write(name: str, content: dict, note: str) -> None:
    path = HERE / name
    path.write_text(json.dumps({'_note': note, **content}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> None:
    write(
        'service-signature.json',
        signing_cases(),
        NOTE,
    )
    write(
        'access-tokens.json',
        token_cases(),
        NOTE + ' 돌릴 때마다 새 키로 서명한다',
    )


if __name__ == '__main__':
    main()
