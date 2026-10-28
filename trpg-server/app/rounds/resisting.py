# trpg-server/app/rounds/resisting.py

"""
닫히는 라운드의 판정 중에 누가 지금 어느 성질을 막는가(#886 ②), 그 성질의 피해를 어떻게 받는가(#886 ③).
구하는 것은 app/tables/resistances.py 다.

판정에 함께 쓰는 것(Judging)에 이미 있는 규칙과 물건과, 장면의 인물과 마리가 들고 있는 정의를 그대로 넘긴다.
DB 를 모른다. 읽기만 한다.
"""

from app.engine.health import Nature
from app.rounds.cast import CastMember
from app.rounds.effects import Judging
from app.rounds.monster_scene import SceneMonster
from app.tables import resistances
from app.tables.models import TableMember


def of_member(judging: Judging, member: TableMember) -> frozenset[str]:
    """앉은 사람의 지금 캐릭터가 막는 성질들. 시트가 있어야 한다(부르는 쪽이 봤다)."""
    return resistances.member_blocked(judging.ruleset, judging.items, member.sheet)


def of_cast(judging: Judging, person: CastMember) -> frozenset[str]:
    """장면의 인물 하나가 막는 성질들."""
    return resistances.npc_blocked(judging.ruleset, judging.items, person.npc, person.definition)


def of_monster(judging: Judging, monster: SceneMonster) -> frozenset[str]:
    """장면의 몬스터 한 마리가 막는 성질들. 타입과 시트의 면역도 든다."""
    return resistances.monster_blocked(judging.ruleset, judging.items, monster.state, monster.definition)


def member_nature(judging: Judging, member: TableMember, nature: str | None) -> Nature | None:
    """앉은 사람의 지금 캐릭터가 그 성질의 피해를 받는 모양(#886 ③). 성질이 없으면 None."""
    return resistances.member_nature(judging.ruleset, judging.items, member.sheet, nature)


def cast_nature(judging: Judging, person: CastMember, nature: str | None) -> Nature | None:
    """장면의 인물 하나가 그 성질의 피해를 받는 모양."""
    return resistances.npc_nature(judging.ruleset, judging.items, person.npc, person.definition, nature)


def monster_nature(judging: Judging, monster: SceneMonster, nature: str | None) -> Nature | None:
    """장면의 몬스터 한 마리가 그 성질의 피해를 받는 모양. 타입과 시트의 면역도 본다."""
    return resistances.monster_nature(judging.ruleset, judging.items, monster.state, monster.definition, nature)
