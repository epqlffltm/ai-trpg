# auth-server/accounts/reserved.py

"""
일반 회원이 쓸 수 없는 예약어 목록.

운영자를 사칭할 수 있는 이름을 한 곳에 모아 둔다.
아이디 검증, 회원가입의 닉네임 검증, 로그인 시도 감시가 모두 이 목록을 쓴다.
목록을 여러 곳에 따로 적으면 한쪽만 고쳤을 때 서로 어긋난다.

판정도 이 파일의 함수 하나다. 로그인에서 탐색으로 보는 이름이 가입에서 막는 이름과 같아야 해서다.
로그인이 더 넓게 보면, 가입이 허용한 이름의 주인이 자기 로그인으로 IP 를 막는다.
"""

import re

RESERVED_NAMES = frozenset(
    {
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
    }
)


# 예약어 그 자체, 또는 예약어 + 밑줄(없어도 된다) + 숫자 1~4자리(admin1, root_2, 운영자0001).
# 숫자는 [0-9] 로 적는다. \d 는 다른 문자의 숫자(٣ 같은 아랍 숫자)까지 받는다.
# 편집 거리, 글자 치환(r00t), 부분 일치는 보지 않는다. 오탐이 늘고 판정을 예측하기 어렵다
_RESERVED_PATTERN = re.compile(
    r'(?:' + '|'.join(re.escape(name) for name in sorted(RESERVED_NAMES)) + r')(?:_?[0-9]{1,4})?'
)


def is_reserved_name(name: str) -> bool:
    """
    이름이 예약어이거나 예약어에 번호만 붙인 변형인지 본다.

    부분 일치로 보면 badminton 처럼 예약어가 우연히 들어간 이름까지 막힌다.
    대소문자와 앞뒤 공백은 무시한다.
    """
    return _RESERVED_PATTERN.fullmatch(name.strip().casefold()) is not None
