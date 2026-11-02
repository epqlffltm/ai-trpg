# shared/server-core/tests/test_contracts.py

"""
공통 규격의 시험 파일(shared/contracts/, #786)을 이 패키지의 코드로 읽는다.

같은 파일을 인증 서버(Django)와 결제 서버(Go)의 테스트도 읽는다. 셋 중 하나라도 어긋나면 그 쪽의 CI 가 떨어진다.
  - service-signature.json: 서버끼리의 서명(server_core/service_auth/signing.py)
  - redaction.json: 로그 가리기(server_core/observability/redaction.py)
  - access-tokens.json: access 토큰의 검증(server_core/auth/tokens.py). 키 목록과 끊긴 세션은 가짜로 넣는다
"""

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest

from server_core.auth.jwks import UnknownKeyError
from server_core.auth.tokens import InvalidTokenError, verify_access_token
from server_core.observability.redaction import is_sensitive_name, scrub_text
from server_core.service_auth.signing import is_valid, sign

CONTRACTS = Path(__file__).resolve().parents[2] / 'contracts'


def load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding='utf-8'))


SIGNATURE = load('service-signature.json')
REDACTION = load('redaction.json')
TOKENS = load('access-tokens.json')


def named(cases: list[dict], key: str = 'name'):
    """경우마다 하나의 시험. 시험의 이름은 그 경우의 key 칸이다."""
    return pytest.mark.parametrize('case', cases, ids=[repr(case[key]) for case in cases])


# --- 서명 ---


@named(SIGNATURE['sign'])
def test_signing_makes_the_same_header(case: dict):
    header = sign(SIGNATURE['secret'], case['sent_at'], case['method'], case['path'], case['body'].encode())

    assert header == case['header']


@named(SIGNATURE['verify'])
def test_signing_accepts_only_the_valid(case: dict):
    secret = case.get('secret', SIGNATURE['secret'])

    valid = is_valid(secret, case['header'], case['method'], case['path'], case['body'].encode(), SIGNATURE['now'])

    assert valid is case['valid']


# --- 로그 가리기 ---


@named(REDACTION['names'])
def test_redaction_knows_the_sensitive_names(case: dict):
    assert is_sensitive_name(case['name']) is case['sensitive']


@named(REDACTION['texts'], key='text')
def test_redaction_scrubs_the_text(case: dict):
    assert scrub_text(case['text'], case['limit']) == case['scrubbed']


# --- access 토큰 ---


class ContractKeys:
    """시험 파일의 키 목록만 아는 가짜 키 저장소."""

    def __init__(self, jwks: dict) -> None:
        self._keys = {key['kid']: jwt.PyJWK(key) for key in jwks['keys']}

    async def get_key(self, kid: str) -> jwt.PyJWK:
        if kid not in self._keys:
            raise UnknownKeyError
        return self._keys[kid]


class NoRevocations:
    """끊긴 세션이 없는 목록."""

    def is_revoked(self, subject: str, version: int) -> bool:
        return False


SETTINGS = SimpleNamespace(jwt_issuer=TOKENS['issuer'], jwt_audience=TOKENS['audience'])


async def verify(token: str):
    return await verify_access_token(token, ContractKeys(TOKENS['jwks']), NoRevocations(), SETTINGS)


@named(TOKENS['accepted'])
async def test_tokens_accept(case: dict):
    claims = await verify(case['token'])

    assert claims.user_id == uuid.UUID(TOKENS['user_id'])
    if 'adult_content' in case:
        assert claims.adult_content is case['adult_content']
    if 'is_operator' in case:
        assert claims.is_operator is case['is_operator']


@named(TOKENS['rejected'])
async def test_tokens_reject(case: dict):
    with pytest.raises(InvalidTokenError):
        await verify(case['token'])
