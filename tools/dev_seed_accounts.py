# tools/dev_seed_accounts.py

"""
개발용 시험 계정을 만들고 access 토큰을 찍는다. dev_seed.py 가 인증 서버의 컨테이너 안에서 돌린다.
이 파일의 글을 auth-server 의 `python manage.py shell -c` 로 넘기고, 계정은 환경 변수 SEED_ACCOUNTS(JSON)로 넘긴다.

이 파일은 Django 의 셸 안에서만 돈다(인증 서버의 모델과 함수를 쓴다).
저장소의 도구 시험(tools/test_*.py)이 불러오지 않는다.

하는 일:
  - 개발 환경(APP_ENVIRONMENT=development)이 아니면 아무것도 하지 않고 멈춘다. staging 의 DB 에 시험 계정을 넣지 않는다
  - 계정마다(SEED_ACCOUNTS 의 아이디, 닉네임, 이메일, 비밀번호) 없으면 만들고, 있으면 비밀번호만 다시 정한다
    메일 인증은 마친 것으로 적는다(가입 3단계와 같다). 비밀번호의 강도는 보지 않는다(개발용이다)
  - 지금의 판의 필수 동의를 적는다. 다시 동의할 것이 남으면 토큰이 인증 서버에만 통해 다른 서버를 부를 수 없다
  - 로그인 없이 토큰을 낸다(issue_token_pair). 로그인의 메일 코드를 거치지 않는다
  - 마지막 줄에 JSON 한 줄을 찍는다: [{"username", "public_id", "access_token"}]. dev_seed.py 가 그 줄을 읽는다
"""

import json
import os
import sys

from accounts.consents import POLICIES, agree, pending_items
from accounts.models import User
from accounts.tokens import issue_token_pair
from django.conf import settings
from django.db import transaction
from django.utils import timezone

# dev_seed.py 가 찾는 줄의 머리
RESULT_PREFIX = 'SEED_RESULT '


def ensure_development() -> None:
    """개발 환경이 아니면 멈춘다."""
    if settings.APP_ENVIRONMENT != 'development':
        sys.exit(f'개발 환경이 아니다(APP_ENVIRONMENT={settings.APP_ENVIRONMENT}). 시험 계정을 만들지 않는다')


def upsert_user(spec: dict) -> User:
    """계정을 만들거나 찾아 비밀번호를 다시 정한다. 메일 인증은 마친 것으로 둔다."""
    user = User.objects.filter(username=spec['username']).first()
    if user is None:
        user = User(username=spec['username'], email=spec['email'], nickname=spec['nickname'])
    user.email_verified_at = user.email_verified_at or timezone.now()
    user.set_password(spec['password'])
    user.save()
    return user


def agree_required(user: User) -> None:
    """다시 동의할 필수 항목에 지금의 판으로 동의한다."""
    now = timezone.now()
    for item in pending_items(user):
        agree(user, item, POLICIES[item].version, now)


def seed_account(spec: dict) -> dict:
    """계정 하나를 갖추고 토큰을 낸다."""
    with transaction.atomic():
        user = upsert_user(spec)
        agree_required(user)
    tokens = issue_token_pair(user)
    return {'username': user.username, 'public_id': str(user.public_id), 'access_token': tokens.access}


def main() -> None:
    ensure_development()
    specs = json.loads(os.environ['SEED_ACCOUNTS'])
    print(RESULT_PREFIX + json.dumps([seed_account(spec) for spec in specs]))


main()
