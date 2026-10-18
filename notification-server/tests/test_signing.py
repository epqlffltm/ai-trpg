# notification-server/tests/test_signing.py

"""
서버끼리의 요청에 붙는 서명(app/service_auth/signing.py)을 검증한다. 결제 서버와 같은 모양이어야 한다.
"""

import hashlib
import hmac

import pytest

from app.service_auth.signing import TOLERANCE_SECONDS, digest, is_valid, sign, split_header

SECRET = 'a-secret-that-is-long-enough-0123'
NOW = 1_800_000_000
PATH = '/api/v1/notification/service/game/notifications'
BODY = b'{"a":1}'


def valid_header(**overrides) -> str:
    values = {'secret': SECRET, 'sent_at': NOW, 'method': 'POST', 'path': PATH, 'body': BODY}
    values.update(overrides)
    return sign(**values)


def test_the_signature_is_the_same_shape_as_the_billing_server():
    # HMAC-SHA256(비밀, "<시각>.<메서드>\n<주소>\n<본문>") 의 16진수
    expected = hmac.new(SECRET.encode(), f'{NOW}.POST\n{PATH}\n'.encode() + BODY, hashlib.sha256).hexdigest()

    assert valid_header() == f't={NOW},v1={expected}'


def test_accepts_its_own_signature():
    assert is_valid(SECRET, valid_header(), 'POST', PATH, BODY, NOW)


@pytest.mark.parametrize('seconds', [-TOLERANCE_SECONDS, TOLERANCE_SECONDS])
def test_accepts_a_clock_difference_up_to_the_tolerance(seconds: int):
    assert is_valid(SECRET, valid_header(sent_at=NOW + seconds), 'POST', PATH, BODY, NOW)


@pytest.mark.parametrize('seconds', [-TOLERANCE_SECONDS - 1, TOLERANCE_SECONDS + 1])
def test_refuses_a_signature_older_or_newer_than_the_tolerance(seconds: int):
    # 가로챈 요청을 나중에 다시 보낼 수 없다
    assert not is_valid(SECRET, valid_header(sent_at=NOW + seconds), 'POST', PATH, BODY, NOW)


@pytest.mark.parametrize(
    ('method', 'path', 'body'),
    [
        ('PUT', PATH, BODY),
        ('POST', '/api/v1/notification/service/billing/notifications', BODY),
        ('POST', PATH, b'{"a":2}'),
    ],
)
def test_refuses_a_signature_of_another_request(method: str, path: str, body: bytes):
    assert not is_valid(SECRET, valid_header(), method, path, body, NOW)


def test_refuses_a_signature_made_with_another_secret():
    assert not is_valid(SECRET, valid_header(secret='another-secret-that-is-long-0123'), 'POST', PATH, BODY, NOW)


@pytest.mark.parametrize('secret', ['', 'short-secret'])
def test_refuses_everything_with_a_missing_or_short_secret(secret: str):
    # 비밀이 비었거나 짧으면 누구나 서명을 만들 수 있다
    assert not is_valid(secret, valid_header(secret=secret), 'POST', PATH, BODY, NOW)


@pytest.mark.parametrize(
    'header',
    [None, '', 'v1=abc', f't={NOW}', f't={NOW};v1=abc', f'v1=abc,t={NOW}', 't=soon,v1=abc', f't=-{NOW},v1=abc'],
)
def test_refuses_a_header_of_the_wrong_shape(header: str | None):
    assert not is_valid(SECRET, header, 'POST', PATH, BODY, NOW)


@pytest.mark.parametrize('sent_at', ['soon', '-1800000000', '١٨٠٠٠٠٠٠٠٠', ''])
def test_refuses_a_signed_time_that_is_not_ascii_digits(sent_at: str):
    # 비밀을 아는 쪽이 서명했더라도 시각이 숫자가 아니면 받지 않는다.
    # isdigit 은 '١٢' 같은 다른 문자의 숫자도 참이다. ASCII 숫자만 받는다
    header = f't={sent_at},v1={digest(SECRET, sent_at, "POST", PATH, BODY)}'

    assert not is_valid(SECRET, header, 'POST', PATH, BODY, NOW)


def test_splits_a_header():
    assert split_header('t=1,v1=ab') == ('1', 'ab')
