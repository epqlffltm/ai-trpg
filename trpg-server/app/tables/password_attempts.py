# trpg-server/app/tables/password_attempts.py

"""
로비의 비밀번호를 무차별 대입으로 맞히지 못하게 틀린 수를 센다(#56).

비밀번호는 4 자부터라 막지 않으면 몇 분이면 뚫린다. 한 번 확인하는 데 scrypt 가 0.2 초쯤 CPU 를 쓰므로
그 자체로 서버를 느리게 하는 공격도 된다. 그래서 확인하기 전에 막는다.

둘을 센다.
  - 한 사람이 한 테이블에 틀린 수. 맞히면 지운다. 몇 번 오타를 낸 사람이 나중에 막히지 않는다
  - 테이블 하나에 모든 사람이 틀린 수. 지우지 않는다. 계정을 여럿 만들어 돌아가며 맞히는 것을 막는다.
    대가로, 누가 일부러 틀려서 그 테이블에 구간 동안 아무도 비밀번호로 못 들어오게 할 수 있다. 초대 코드로는 들어온다
막힌 뒤에는 맞는 비밀번호도 받지 않는다(확인 자체를 하지 않는다). 세는 곳(Redis)에 닿지 못하면 막는다(503).

비밀번호가 없는 테이블은 세지 않는다. 초대 코드로 들어오는 길은 비밀번호를 묻지 않으므로 세지 않는다.
"""

import uuid

from app.limits.setup import Limiting
from app.tables.building import check_table_password
from app.tables.errors import WrongPasswordError
from app.tables.models import GameTable


def password_subjects(table_id: uuid.UUID, user_id: uuid.UUID) -> tuple[str, str]:
    """세는 대상. (이 사람과 이 테이블, 이 테이블)."""
    return f'{table_id}:{user_id}', str(table_id)


async def guarded_password_check(
    table: GameTable, user_id: uuid.UUID, password: str | None, limiting: Limiting
) -> None:
    """
    너무 많이 틀렸으면 TooManyAttempts, 세는 곳에 닿지 못하면 LimitsUnavailable, 비밀번호가 틀렸으면 WrongPasswordError.

    틀리면 둘 다 하나씩 세고, 맞히면 이 사람의 수만 지운다.
    """
    if table.password_hash is None:
        return
    limiter, limits = limiting.limiter, limiting.limits
    mine, everyone = password_subjects(table.id, user_id)
    await limiter.ensure_not_blocked(limits.password_per_user, mine)
    await limiter.ensure_not_blocked(limits.password_per_table, everyone)
    try:
        await check_table_password(table, password)
    except WrongPasswordError:
        await limiter.count_failure(limits.password_per_user, mine)
        await limiter.count_failure(limits.password_per_table, everyone)
        raise
    await limiter.clear(limits.password_per_user, mine)
