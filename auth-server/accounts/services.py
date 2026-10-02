# auth-server/accounts/services.py

"""
accounts 앱의 도메인 로직.

HTTP 를 모른다. 요청과 응답 객체를 받지 않고, 검증이 끝난 값만 받는다.
그래서 뷰 없이도 테스트하고 다른 곳(관리 명령 등)에서 다시 쓸 수 있다.
"""

from django.db import IntegrityError, transaction

from accounts.models import User


class DuplicateAccountError(Exception):
    """아이디, 이메일, 닉네임 중 하나가 이미 쓰이고 있어 계정을 만들 수 없다."""


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