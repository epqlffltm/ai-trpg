# game-server/tests/test_table_passwords.py

"""
테이블의 비밀번호를 저장할 모양으로 바꾸고 확인하는 일을 검증한다. DB 를 쓰지 않는다.
"""

import base64
import hashlib

from app.tables.passwords import SCHEME, hash_password, verify_password

PASSWORD = '열려라 참깨'


def test_the_stored_value_does_not_contain_the_password():
    stored = hash_password(PASSWORD)

    assert PASSWORD not in stored
    # 어느 방식으로, 어떤 비용으로 계산했는지 함께 적혀 있다
    assert stored.startswith(f'{SCHEME}$')
    assert len(stored.split('$')) == 6


def test_verifies_the_right_password_only():
    stored = hash_password(PASSWORD)

    assert verify_password(PASSWORD, stored)
    assert not verify_password('열려라 들깨', stored)
    assert not verify_password('', stored)
    # 앞뒤 공백도 비밀번호의 일부다
    assert not verify_password(f' {PASSWORD}', stored)


def test_the_same_password_is_stored_differently_each_time():
    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)

    # 소금이 매번 달라서 저장된 값도 다르다. 같은 비밀번호를 쓰는 테이블을 값으로 알아볼 수 없다
    assert first != second
    assert verify_password(PASSWORD, first)
    assert verify_password(PASSWORD, second)


def test_a_value_of_another_scheme_never_matches():
    stored = hash_password(PASSWORD).replace(SCHEME, 'plain', 1)

    assert not verify_password(PASSWORD, stored)


def test_verifies_with_the_cost_written_in_the_stored_value():
    # 비용을 낮춰서 만든 값. 나중에 기본 비용을 올려도 옛 값은 적힌 비용으로 확인한다
    _, _, _, _, salt, _ = hash_password(PASSWORD).split('$')
    key = hashlib.scrypt(PASSWORD.encode(), salt=base64.b64decode(salt), n=2**10, r=8, p=1, dklen=32)
    cheap = f'{SCHEME}${2**10}$8$1${salt}${base64.b64encode(key).decode()}'

    assert verify_password(PASSWORD, cheap)
