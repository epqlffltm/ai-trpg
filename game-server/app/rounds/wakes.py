# game-server/app/rounds/wakes.py

"""
쓰러져 있는 동안 물건을 빼앗긴 NPC 가 깨어날 때의 반응(#494). 의식이 없어 빼앗길 때는 몰랐다(app/rounds/loots.py).

  - 깨어나는 것은 판정의 회복으로 쓰러짐에서 살아남으로 바뀔 때다(app/rounds/checks.py 의 npc_outcome).
    NPC 의 HP 를 올리는 길은 그것뿐이다.
  - 쓰러진 동안 빼앗겼으면(table_npcs.robbed_round) 백면체를 한 번 굴린다. 확률은 규칙의 robbed_wake 다.
    hostile 이하면 적대, 그다음 wary 만큼이면 경계, 나머지는 눈치채지 못한다.
  - 태도는 더 날 선 쪽으로만 바뀐다. 이미 적대면 그대로, 경계하던 인물은 적대가 나와야 바뀐다.
  - 굴린 뒤에는 적어 둔 것을 비운다. 또 쓰러져 빼앗기지 않는 한 다시 굴리지 않는다.
  - 규칙에 반응이 없으면(robbed_wake 가 None) 굴리지 않는다. 적어 둔 것은 비운다.

판정 안에서 한 번 부른다. 결과는 선언의 outcome 에 적히고 그 뒤로는 읽기만 한다. 서술을 다시 맡겨도 다시 굴리지 않는다.
DB 를 모른다. NPC 의 태도와 적어 둔 것을 고친다. 저장하지 않는다.
"""

import uuid

from app.assets.models import NpcAttitude
from app.engine.drops import PERCENT
from app.engine.ruleset import RobbedWake
from app.rounds.cast import find_cast_member
from app.rounds.effects import Judging
from app.tables import npcs
from app.tables.models import NpcStatus, TableNpc
from app.tables.npc_attitudes import change_attitude, sharpens

# 깨어나 빼앗긴 것을 알아채 태도가 바뀐 까닭. npc_attitude_changed 이벤트의 reason 에 적는다
ROBBED_WHILE_DOWN = 'robbed_while_down'


def woke_now(effect: dict) -> bool:
    """이 변화로 쓰러져 있던 NPC 가 일어났는가."""
    return effect['status_before'] == NpcStatus.DOWNED and effect['status'] == NpcStatus.ALIVE


def reaction_of(rule: RobbedWake, roll: int) -> NpcAttitude | None:
    """백면체의 눈으로 정한 반응. hostile 이하면 적대, 그다음 wary 만큼이면 경계, 나머지는 None(눈치채지 못함)."""
    if roll <= rule.hostile:
        return NpcAttitude.HOSTILE
    if roll <= rule.hostile + rule.wary:
        return NpcAttitude.WARY
    return None


def react(npc: TableNpc, reaction: NpcAttitude | None) -> dict | None:
    """반응이 지금 태도보다 날 서 있으면 태도를 바꾸고 이벤트에 적을 모양을 돌려준다. 아니면 None."""
    if reaction is None or not sharpens(NpcAttitude(npc.attitude), reaction):
        return None
    return change_attitude(npc, reaction, ROBBED_WHILE_DOWN)


def wake_after(judging: Judging, effect: dict | None) -> dict | None:
    """
    NPC 의 변화 뒤에 깨어날 때의 반응을 굴린다. 굴렸으면 결과의 문서를, 아니면 None 을 돌려준다.

    roll 은 백면체의 눈, reaction 은 그 눈이 정한 반응(hostile, wary, 또는 None),
    attitude_change 는 실제로 바뀐 태도다(이미 그만큼 날 서 있었으면 None).
    """
    if effect is None or not woke_now(effect):
        return None
    person = find_cast_member(judging.cast, uuid.UUID(effect['entry_id']))
    if person is None or not npcs.take_robbed(person.npc):
        return None
    rule = judging.ruleset.robbed_wake
    if rule is None:
        return None
    roll = judging.dice.roll(PERCENT)
    reaction = reaction_of(rule, roll)
    return {
        'entry_id': str(person.entry_id),
        'name': person.name,
        'roll': roll,
        'reaction': reaction,
        'attitude_change': react(person.npc, reaction),
    }
