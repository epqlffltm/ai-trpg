# auth-server/accounts/roles.py

"""
계정의 역할을 읽는다(#389). 고치지 않는다. 토큰(tokens.py)이 access 토큰의 roles 에 싣는다.

운영자는 Django 그룹 operators 에 든 계정이다. 넣고 빼는 것은 관리자 화면(/admin/)의 그룹에서 한다.
is_staff(관리자 화면에 들어가는 권한)와 나눈다. 관리자 화면을 쓰는 권한과 서비스의 운영 권한은 다른 것이라,
필요한 권한만 주려는 것이다. 운영자가 다른 서버에서 무엇을 더 하는지는 docs/architecture/operators.md 에 있다.
"""

from accounts.models import User

# 운영자의 그룹 이름. 마이그레이션 0019 가 만든다
OPERATORS_GROUP = 'operators'
# 토큰에 싣는 운영자의 역할 이름. 다른 서버는 목록에 이 글자가 정확히 있을 때만 운영자로 본다
OPERATOR_ROLE = 'operator'


def roles_of(user: User) -> list[str]:
    """그 계정의 역할들. 운영자면 ["operator"], 아니면 빈 목록이다."""
    if user.groups.filter(name=OPERATORS_GROUP).exists():
        return [OPERATOR_ROLE]
    return []
