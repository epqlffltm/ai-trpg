# board-server/tests/test_contracts.py

"""
공통 규격의 시험 파일(shared/contracts/service-signature.json, #786)을 게시판 서버의 서명 확인으로 읽는다.

게시판은 머리말을 읽는 법을 따로 둔다(app/core/service_auth.py, NestJS 로 쓰던 때와 같게).
서명의 셈은 공용 코드의 것이라 같지만, 받는 모양이 공용 코드, 인증 서버, 결제 서버와 같은지는 이 파일이 본다.
로그 가리기와 토큰의 검증은 공용 코드(shared/server-core)의 것을 그대로 쓰므로 그쪽의 테스트가 본다. DB 를 쓰지 않는다.
"""

import json
from pathlib import Path

import pytest

from app.core.service_auth import is_valid_signature

CONTRACTS = Path(__file__).resolve().parents[2] / 'shared' / 'contracts'
CONTRACT = json.loads((CONTRACTS / 'service-signature.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CONTRACT['verify'], ids=[case['name'] for case in CONTRACT['verify']])
def test_the_signature_follows_the_shared_contract(case: dict):
    secret = case.get('secret', CONTRACT['secret'])

    valid = is_valid_signature(
        secret, case['header'], case['method'], case['path'], case['body'].encode(), CONTRACT['now']
    )

    assert valid is case['valid']
