# trpg-server/app/rounds/friendly_fire.py

"""
앉은 사람끼리 해치는 행동(#803)을 받을 때와 라운드를 닫을 때 보는 것.

해치는 행동은 셋이다. 타격(harm)이 있는 판정으로 치기, 해로운 물건(피해, 부상)을 쓰기, 해로운 물건을 던지기.
얼마나 해칠 수 있는지는 테이블의 설정과 맞는 쪽의 설정 중 낮은 것이다(app/tables/friendly_fire.py).
자기 자신에게 하는 것은 늘 된다.

  - 받을 때: 맞는 사람이 앉아 있고 살아 있어야 하고, 같은 장소에 있어야 한다(맵이 있는 판).
    동료면 끔이면 409 friendly_fire_off, 쓰러져 있으면 409 ally_down 이다.
    장난만이면 오래 가는 부상이나 결손을 노릴 수 없다(409 friendly_fire_prank).
  - 닫을 때: 받은 뒤에 설정이 바뀌었거나 맞는 사람이 떠나거나 쓰러졌을 수 있다. 굴리기 전에 다시 본다.
    해칠 수 없으면 굴리지 않고 그 까닭을 적는다(target_gone, user_id 와 reason). 장난이면 상한을 지킨다.

DB 를 모른다.
"""

import uuid

from app.engine import injury as injury_rules
from app.engine.ruleset import Healing, Ruleset
from app.rounds.effects import Judging
from app.rounds.errors import ActionTargetError, Conflict, RoundConflictError
from app.tables import friendly_fire, sheets
from app.tables import state as table_state
from app.tables.models import FriendlyFire, GameTable, TableMember


class AllyGone:
    """닫을 때 동료를 해칠 수 없는 까닭. 결과의 target_gone.reason 에 적는다."""

    # 테이블을 떠났다
    LEFT = 'left'
    # 차례가 오기 전에 죽었다
    DEAD = 'dead'
    # 쓰러져 있다. 쓰러진 동료는 해치지 않는다
    DOWNED = 'downed'
    # 다른 장소에 있다
    ELSEWHERE = 'elsewhere'
    # 받은 뒤에 테이블이나 맞는 쪽이 받아들이지 않게 바꿨다
    FRIENDLY_FIRE_OFF = 'friendly_fire_off'


def stands_together(actor: TableMember, target: TableMember) -> bool:
    """두 캐릭터가 같은 장소에 있는가. 맵이 없는 판이면 둘 다 장소가 없어 같다."""
    return actor.sheet is not None and target.sheet is not None and actor.sheet.place_id == target.sheet.place_id


def require_harmable(table: GameTable, actor: TableMember, target_id: uuid.UUID) -> tuple[TableMember, FriendlyFire]:
    """
    받을 때. actor 가 target_id 를 해칠 수 있는지 보고, 맞는 사람과 해칠 수 있는 정도를 돌려준다.

    앉은 사람이 아니거나 다른 장소에 있으면 ActionTargetError(target), 죽었으면 RoundConflictError(ally_dead).
    동료면 받아들이지 않으면 friendly_fire_off, 쓰러져 있으면 ally_down 이다.
    """
    target = table_state.find_member(table, target_id)
    if target is None or not stands_together(actor, target):
        raise ActionTargetError('target')
    if sheets.is_dead(target):
        raise RoundConflictError(Conflict.ALLY_DEAD)
    level = friendly_fire.level_toward(table, actor.user_id, target)
    if level == FriendlyFire.OFF:
        raise RoundConflictError(Conflict.FRIENDLY_FIRE_OFF)
    if target.user_id != actor.user_id and sheets.is_downed_alive(target):
        raise RoundConflictError(Conflict.ALLY_DOWN)
    return target, level


def is_lasting_injury(ruleset: Ruleset, key: str) -> bool:
    """오래 가는 부상이나 결손인가. 규칙에 없는 부상이면 아니다(받을 때 노릴 수 있는지 먼저 봤다)."""
    definition = injury_rules.find_injury(ruleset, key)
    return definition is not None and definition.healing != Healing.ROUNDS


def require_prank_aim(ruleset: Ruleset, level: FriendlyFire, aim: str | None) -> None:
    """받을 때. 장난만이면 짧은 부상만 노린다. 오래 가는 부상이나 결손을 노렸으면 RoundConflictError."""
    if friendly_fire.is_prank(level) and aim is not None and is_lasting_injury(ruleset, aim):
        raise RoundConflictError(Conflict.FRIENDLY_FIRE_PRANK)


def gone_document(target: TableMember | None, target_id: uuid.UUID, reason: str) -> dict:
    """해칠 수 없었던 것을 결과의 target_gone 에 적을 모양. 떠났으면 이름이 없다."""
    return {'user_id': str(target_id), 'name': target.character_name if target else None, 'reason': reason}


def gone_reason(judging: Judging, actor: TableMember, target: TableMember | None) -> str | None:
    """닫을 때 actor 가 target 을 해칠 수 없으면 그 까닭. 해칠 수 있으면 None."""
    if target is None or target.sheet is None:
        return AllyGone.LEFT
    if sheets.is_dead(target):
        return AllyGone.DEAD
    if not stands_together(actor, target):
        return AllyGone.ELSEWHERE
    if target.user_id == actor.user_id:
        return None
    if sheets.is_downed_alive(target):
        return AllyGone.DOWNED
    if friendly_fire.level_toward(judging.table, actor.user_id, target) == FriendlyFire.OFF:
        return AllyGone.FRIENDLY_FIRE_OFF
    return None


def ally_gone(judging: Judging, actor: TableMember, target_id: uuid.UUID) -> dict | None:
    """닫을 때. 해칠 동료를 지금 해칠 수 없으면 그 까닭을 문서로. 해칠 수 있으면 None."""
    target = table_state.find_member(judging.table, target_id)
    reason = gone_reason(judging, actor, target)
    return None if reason is None else gone_document(target, target_id, reason)


def is_prank_toward(judging: Judging, actor: TableMember, target: TableMember) -> bool:
    """닫을 때. actor 가 target 에게 하는 것이 장난만인가. 상한(HP 1, 짧은 부상)을 지킨다."""
    return friendly_fire.is_prank(friendly_fire.level_toward(judging.table, actor.user_id, target))
