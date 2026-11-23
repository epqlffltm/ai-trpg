# trpg-server/app/tables/away.py

"""
자리 비움의 수와 문턱(#1345). 선언을 연속으로 내지 않은 라운드의 수를 테이블의 행(away_counts)에서 읽는다.

세고 빼는 일은 app/rounds/presence.py 다. 여기는 청구(app/billing/charges.py)도 읽으므로 무거운 것을 불러오지 않는다.
"""

import uuid

from app.tables.models import GameTable

# 연속으로 내지 않으면 서술 값을 걸지 않는 라운드의 수
AWAY_ROUNDS = 2
# 연속으로 내지 않으면 자리에서 빼는 라운드의 수
REMOVE_ROUNDS = 5


def missed(table: GameTable, user_id: uuid.UUID) -> int:
    """그 사람이 연속으로 내지 않은 라운드의 수."""
    return int(table.away_counts.get(str(user_id), 0))


def is_away(table: GameTable, user_id: uuid.UUID) -> bool:
    """자리를 비운 사람인가. 연속 AWAY_ROUNDS 번 내지 않았다. 서술 값을 걸지 않는다."""
    return missed(table, user_id) >= AWAY_ROUNDS
