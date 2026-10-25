# board-server/app/core/ids.py

"""
글, 댓글, 신고의 번호. 주소와 응답에는 숫자를 글자로 싣는다(자바스크립트의 수가 큰 번호를 잃지 않게).

주소의 번호는 모양을 먼저 본다. 모양이 아니면 DB 에 묻지 않고 "없다"로 답한다.
숫자가 아닌 값이나 NUL 글자를 그대로 물으면 DB 가 오류를 내고, 그것은 500 이 된다.
"""

import re

# 1 부터 시작하는 18자리까지의 수. bigint 에 들어간다. ASCII 숫자만 받는다(파이썬의 \d 는 다른 글자의 숫자도 받는다)
RECORD_ID = re.compile(r'\A[1-9][0-9]{0,17}\Z')


def parse_record_id(value: str) -> int | None:
    """주소의 번호를 수로. 모양이 아니면 None 이다."""
    return int(value) if RECORD_ID.fullmatch(value) else None


def record_id(value: int | None) -> str | None:
    """응답에 싣는 번호."""
    return None if value is None else str(value)
