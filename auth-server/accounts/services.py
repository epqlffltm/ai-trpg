# auth-server/accounts/services.py

"""
accounts 앱의 도메인 로직.

HTTP 를 모른다. 요청과 응답 객체를 받지 않고, 검증이 끝난 값만 받는다.
그래서 뷰 없이도 테스트하고 다른 곳(관리 명령 등)에서 다시 쓸 수 있다.
"""

from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction

from accounts.models import User


class DuplicateAccountError(Exception):
    """
    아이디, 이메일, 닉네임 중 하나가 이미 쓰이고 있어 계정을 만들 수 없다.
    """
    
class InvalidCredentialsError(Exception):
    """
    아이디와 비밀번호로 사용자를 확인하지 못했다.

    아이디가 없는 경우, 비밀번호가 틀린 경우, 비활성 계정인 경우를 구분하지 않는다.
    구분하면 호출한 쪽이 그 차이를 응답에 실어 가입 여부를 알려 주게 된다.
    """


def register_user(*, username: str, email: str, nickname: str, password: str) -> User:
    """
    회원 계정을 만든다.

    Serializer 의 사전 조회를 통과했더라도, 그 사이에 다른 요청이 같은 값으로 먼저
    저장할 수 있다. 그 경우 DB 의 유니크 제약이 막고, 여기서 도메인 예외로 바꾼다.
    """
    try:
        # 실패한 INSERT 가 바깥 트랜잭션까지 망가뜨리지 않도록 따로 감싼다
        with transaction.atomic():
            # create_user 가 비밀번호를 해싱해 저장한다
            return User.objects.create_user(
                username=username,
                email=email,
                nickname=nickname,
                password=password,
            )
    except IntegrityError as exc:
        raise DuplicateAccountError from exc

def authenticate_user(*, username: str, password: str) -> User:
    """
    아이디와 비밀번호가 맞는 사용자를 돌려준다.

    Django 의 authenticate 를 쓴다. 비밀번호 비교뿐 아니라 두 가지를 대신 해 준다.
    - 없는 아이디여도 해싱을 한 번 수행해, 응답 시간으로 가입 여부가 드러나지 않게 한다.
    - is_active 가 False 인 계정은 비밀번호가 맞아도 거부한다.
    """
    user = authenticate(username=username, password=password)
    if user is None:
        raise InvalidCredentialsError
    return user