# tools/vm_seed_token.py

"""
VM 테스트의 작품을 만들 운영자의 access 토큰을 찍는다. vm_seed.py 가 인증 서버의 컨테이너 안에서 돌린다.
SSH 로 이 파일의 글을 컨테이너의 `python -` 에 넘기고, 아이디는 환경 변수 SEED_CREATOR 로 넘긴다.

이 파일은 인증 서버의 컨테이너 안에서만 돈다(Django 와 인증 서버의 모델을 쓴다).
저장소의 도구 시험(tools/test_*.py)이 불러오지 않는다.

하는 일:
  - 운영 환경(APP_ENVIRONMENT=production)이면 아무것도 하지 않고 멈춘다
  - 그 아이디의 계정을 찾는다. 없거나, 쓰지 못하거나(정지, 탈퇴), 운영자가 아니면 멈춘다.
    캐릭터와 세계관은 지금 운영자만 만들고 공개한다
  - 다시 동의할 필수 항목이 남았으면 멈춘다. 그 토큰은 인증 서버에만 통한다. 남 대신 동의하지 않는다.
    화면에서 한 번 로그인하면 동의를 받는다
  - 계정도 비밀번호도 바꾸지 않는다. 로그인 없이 토큰을 낸다(issue_token_pair). 메일 코드를 거치지 않는다
  - 마지막 줄에 JSON 한 줄을 찍는다: {"access_token"}. vm_seed.py 가 그 줄을 읽는다
"""

import json
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from accounts.consents import pending_items  # noqa: E402
from accounts.models import User  # noqa: E402
from accounts.roles import OPERATOR_ROLE, roles_of  # noqa: E402
from accounts.tokens import issue_token_pair  # noqa: E402
from django.conf import settings  # noqa: E402

# vm_seed.py 가 찾는 줄의 머리
RESULT_PREFIX = 'SEED_TOKEN '


def ensure_not_production() -> None:
    if settings.APP_ENVIRONMENT == 'production':
        sys.exit('운영 환경이다. 테스트 작품의 토큰을 내지 않는다')


def find_creator(username: str) -> User:
    """만들 사람. 쓸 수 있는 운영자여야 하고 다시 동의할 것이 없어야 한다."""
    user = User.objects.filter(username=username).first()
    if user is None or not user.is_active or user.withdrawn_at is not None:
        sys.exit(f'쓸 수 있는 계정이 없다: {username}')
    if OPERATOR_ROLE not in roles_of(user):
        sys.exit(f'운영자가 아니다: {username}. 그룹 operators 에 넣는다')
    if pending := list(pending_items(user)):
        sys.exit(f'다시 동의할 것이 남았다: {pending}. 화면에서 로그인해 동의를 마친다')
    return user


def main() -> None:
    ensure_not_production()
    user = find_creator(os.environ['SEED_CREATOR'])
    print(RESULT_PREFIX + json.dumps({'access_token': issue_token_pair(user).access}))


main()
