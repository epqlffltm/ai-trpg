# auth-server/accounts/reserved.py

"""
일반 회원이 쓸 수 없는 예약어 목록.

운영자를 사칭할 수 있는 이름을 한 곳에 모아 둔다.
아이디 검증, 회원가입의 닉네임 검증, 로그인 시도 감시가 모두 이 목록을 쓴다.
목록을 여러 곳에 따로 적으면 한쪽만 고쳤을 때 서로 어긋난다.
"""

RESERVED_NAMES = frozenset({
    # 영문. 아이디와 닉네임 양쪽에 해당한다
    'admin',
    'administrator',
    'root',
    'superuser',
    'system',
    'staff',
    'support',
    'operator',
    'moderator',
    'manager',
    'master',
    'official',
    'gamemaster',
    'gm',
    # 한글. 아이디는 영문만 허용하므로 닉네임에만 해당한다
    '운영자',
    '관리자',
    '게임마스터',
})


def is_reserved_name(name: str) -> bool:
    """
    이름이 예약어와 정확히 일치하는지 본다.

    부분 일치로 보면 badminton 처럼 예약어가 우연히 들어간 이름까지 막힌다.
    대소문자와 앞뒤 공백은 무시한다.
    """
    return name.strip().casefold() in RESERVED_NAMES