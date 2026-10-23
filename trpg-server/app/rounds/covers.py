# trpg-server/app/rounds/covers.py

"""
엄폐하기(#276 의 커버 세이브). 지금 장소의 숨을 곳에 엄폐하는 행동(cover)을 받고, 라운드가 닫힐 때 커버를 정한다.

  - 받기(accept_cover): 세이브 방식의 룰북이어야 한다(아니면 ActionNotInRulesError(kind)). 맵에 서 있어야 하고
    (아니면 RoundConflictError(not_on_map)), 그 장소에 커버가 있어야 한다(아니면 RoundConflictError(no_cover)).
    장소의 커버는 테이블의 맵에 보인다. 숨길 것이 없어 가르지 않는다.
  - 커버가 드는 때(covers_of): 라운드가 닫힐 때, 판정을 시작하기 전에 정한다. 엄폐를 선언한 사람은 그 라운드 동안
    서 있는 장소의 커버를 갖는다. 차례를 기다리지 않는다. 숨는 것은 공격에 앞선다. 몬스터가 먼저 쳐도 커버가 든다.
    커버는 엔진의 상태다. 서술이 "벽 뒤에 숨었다"고 써도 생기지 않는다.
  - 차례(judge_cover): 숨은 곳과 그 커버를 결과에 적는다. 굴림이 없다.
  - 막는 법: 맞힌 뒤의 세이브에서 아머, 커버, 불굴 중 큰 값으로 한 번 굴린다. 관통하면 커버로도 막지 못한다
    (app/engine/armor.py, app/rounds/blows.py).
앉은 사람만 엄폐한다. NPC 와 몬스터가 엄폐하는지(언제 숨는지)는 따로 정한다(인물의 자리 #282 가 생긴 뒤의 일).

DB 를 모른다. 이미 읽어 온 테이블과 판을 받는다.
"""

import uuid

from app.assets.scenarios.snapshot import Snapshot, cover_at, read_snapshot
from app.engine import action as actions
from app.engine.action import CoverAction
from app.engine.ruleset import ArmorMode, Ruleset
from app.rounds.effects import Judging
from app.rounds.errors import ActionNotInRulesError, Conflict, RoundConflictError
from app.rounds.map_actions import standing_place
from app.rounds.models import Declaration
from app.tables import places
from app.tables.models import GameTable, TableMember


def require_save_rules(ruleset: Ruleset) -> None:
    """세이브 방식의 규칙인가. 아니면 ActionNotInRulesError(kind). 커버는 세이브의 하나다."""
    if ruleset.armor is None or ruleset.armor.mode != ArmorMode.SAVE:
        raise ActionNotInRulesError('kind')


def accept_cover(table: GameTable, member: TableMember, ruleset: Ruleset, action: CoverAction) -> dict:
    """
    엄폐하는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 세이브 방식의 규칙이 아니면 ActionNotInRulesError(kind).
      - 맵에 서 있지 않으면 RoundConflictError(not_on_map).
      - 서 있는 장소에 커버가 없으면 RoundConflictError(no_cover).
    """
    require_save_rules(ruleset)
    here = standing_place(member)
    if cover_at(read_snapshot(table.content), here) <= 0:
        raise RoundConflictError(Conflict.NO_COVER)
    return action.model_dump(mode='json')


def covering(declaration: Declaration) -> bool:
    """엄폐를 선언했는가."""
    return declaration.action is not None and isinstance(actions.read_action(declaration.action), CoverAction)


def covers_of(snapshot: Snapshot | None, rolling: list[tuple[TableMember, Declaration]]) -> dict[uuid.UUID, int]:
    """
    이번 라운드에 엄폐한 사람들과 그 커버(user_id → 커버). 판정을 시작하기 전에 한 번 정한다.

    서 있는 장소의 커버다. 선언을 받은 뒤 방장이 옮겼으면 옮긴 곳의 것이다. 커버가 없는 곳이면 넣지 않는다.
    """
    if snapshot is None:
        return {}
    found = {}
    for member, declaration in rolling:
        cover = cover_at(snapshot, member.sheet.place_id) if covering(declaration) else 0
        if cover > 0:
            found[member.user_id] = cover
    return found


def judge_cover(judging: Judging, member: TableMember) -> dict:
    """
    엄폐한 사람의 차례. 숨은 곳과 그 커버를 적는다. 커버는 판정을 시작할 때 이미 들었다(covers_of).

    커버가 0 이면(그사이에 커버가 없는 곳으로 옮겨졌다) 숨지 못한 것이다.
    """
    cover = judging.covers.get(member.user_id, 0)
    return {'cover': {'place': places.describe(judging.snapshot, member.sheet.place_id), 'value': cover}}
