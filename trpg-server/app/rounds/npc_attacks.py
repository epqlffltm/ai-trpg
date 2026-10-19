# trpg-server/app/rounds/npc_attacks.py

"""
NPC 의 차례(#487). 싸움이 붙은 적대 인물이 캐릭터 하나를 공격 하나로 친다. 몬스터의 차례와 같은 모양이다
(app/rounds/monster_attacks.py). 다른 것은 차례를 받는 인물, 대상을 고르는 법, 부상의 영향이다.

차례를 받는 인물(can_act). 라운드를 닫기 시작할 때 본다. 엔진의 상태만 본다. 서술(AI)이 정하지 않는다.
  - 이번 장면에 나왔고, 살아 있고(쓰러지지 않았고), 적대이고, 싸움이 붙었고(fought_round), 시트에 공격이 있다.
  - 적대이기만 한 인물(들켰는데 on_caught 가 hostile, 깨어나 적대가 된 인물)은 싸움이 붙기 전에는 치지 않는다.
  - 이번 라운드에 싸움이 붙은 인물은 다음 라운드부터 친다. 차례는 판정을 시작하기 전에 정한다.
  - 싸움은 끝나지 않는다(fought_round 를 비우지 않는다). 장면에서 빠지거나 쓰러지거나 죽으면 치지 않는다.

차례가 오면 먼저 칠 수 있는지 본다. 앞 차례에 쓰러지거나 죽었으면, 입은 부상 때문에 움직이지 못하면(기절 같은 것),
칠 캐릭터가 없으면 굴리지 않는다(skipped). 앉은 사람이 그런 부상이면 행동을 붙이지 못하는 것과 같다.
대상. NPC 는 장소가 없다(#282). 앉은 사람의 서 있는(쓰러지지 않은) 캐릭터가 모두 대상이 될 수 있다.
  1. 이번 라운드에 이 인물에게서 훔치다 들킨 도둑(app/rounds/steals.py). 몬스터와 같다
  2. 이번 라운드에 이 인물과 싸운 사람(타격으로 겨눴다) 중에서 서버의 주사위로
  3. 그 밖의 서 있는 캐릭터 중에서 서버의 주사위로
  앞의 것이 칠 수 있는 대상이 아니면(쓰러졌다) 다음 것으로 간다. 고를 것이 하나뿐이면 굴리지 않는다.
판정은 인물의 점수와 공격의 난이도로 굴린다. 몬스터와 달리 인물은 부상을 입으므로 그 영향을 받는다.
맞히면 그 공격의 양의 등급만큼 피해를 준다. 피해, 쓰러짐, 부상 표는 앉은 사람의 것과 같다(change_sheet).
친 대상과는 싸운 것으로 적는다(mark_npc_fight).
DB 를 모른다. 시트를 고친다. 저장하지는 않는다.
"""

from app.assets.models import NpcAttitude
from app.assets.scenarios.snapshot import AttackSnapshot
from app.engine import check as checks
from app.engine.check import HinderedCheck
from app.engine.dice import choose
from app.engine.health import ChangeKind
from app.rounds import injuries as round_injuries
from app.rounds.cast import CastMember
from app.rounds.checks import change_sheet
from app.rounds.effects import Judging, mark_npc_fight
from app.rounds.monster_attacks import Skipped, attack_outcome
from app.tables import sheets
from app.tables.models import NpcStatus, TableMember

# 입은 부상 때문에 움직이지 못했다(기절 같은 것). 몬스터는 부상을 입지 않아 이 까닭이 없다
INCAPACITATED = 'incapacitated'


def is_fighting(person: CastMember) -> bool:
    """이 인물이 일행과 싸우는 중인가. 적대이고 싸움이 붙었다(한 번 붙으면 끝나지 않는다)."""
    npc = person.npc
    return npc.attitude == NpcAttitude.HOSTILE and npc.fought_round is not None


def can_act(person: CastMember) -> bool:
    """이 인물이 이번 라운드에 차례를 받는가. 살아 있고, 싸우는 중이고, 시트에 공격이 있어야 한다."""
    armed = person.definition is not None and bool(person.definition.attacks)
    return person.npc.status == NpcStatus.ALIVE and armed and is_fighting(person)


def stopped_by(judging: Judging, person: CastMember) -> str | None:
    """차례가 왔을 때 이 인물이 움직이지 못하는 까닭. 움직일 수 있으면 None."""
    if person.npc.status == NpcStatus.DEAD:
        return Skipped.DEAD
    if person.npc.status == NpcStatus.DOWNED:
        return Skipped.DOWNED
    if round_injuries.is_incapacitated(judging.ruleset, person.npc.injuries):
        return INCAPACITATED
    return None


def standing_members(judging: Judging) -> list[TableMember]:
    """칠 수 있는 캐릭터들. 앉은 사람 중 시트가 있고 쓰러지지도 죽지도 않았다. 장소는 보지 않는다. 앉은 순서다."""
    return [
        member
        for member in judging.table.members
        if member.sheet is not None and not sheets.is_dead(member) and not sheets.is_downed_alive(member)
    ]


def pick_victim(judging: Judging, person: CastMember, victims: list[TableMember]) -> TableMember:
    """칠 대상. 들킨 도둑, 그다음 이번 라운드에 이 인물과 싸운 사람, 그다음 서 있는 누구나다. 주사위는 서버의 것이다."""
    thief = judging.provoked.get(person.entry_id)
    caught = next((victim for victim in victims if victim.user_id == thief), None)
    if caught is not None:
        return caught
    fought = judging.fights.get(person.entry_id, set())
    opponents = [victim for victim in victims if victim.user_id in fought]
    return choose(opponents or victims, judging.dice)


def roll_attack(judging: Judging, person: CastMember, attack: AttackSnapshot) -> HinderedCheck:
    """
    공격 하나의 판정. 인물의 그 능력치 점수와 공격의 난이도로 굴린다. 인물이 입은 부상의 영향을 받는다.

    능력치와 난이도는 게시할 때 판의 규칙에 있는 것인지 확인했다(app/assets/scenarios/publishing.py).
    """
    ruleset = judging.ruleset
    difficulty = checks.find_difficulty(ruleset, attack.difficulty)
    hindrance = round_injuries.hindrance_for(ruleset, person.npc.injuries, attack.ability)
    score = person.npc.abilities[attack.ability]
    return checks.resolve_hindered(ruleset, score, difficulty, judging.dice, hindrance)


def take_npc_turn(judging: Judging, person: CastMember) -> dict:
    """
    인물 하나의 차례를 판정한다. 차례의 outcome 에 적을 문서를 돌려준다.

    움직이지 못하면 {'skipped': 까닭} 이다. 대상, 공격, 판정, 피해의 차례로 주사위를 굴린다.
    문서는 몬스터의 것(attack_outcome)에 부상의 영향(hindrance)을 더한 것이다.
    """
    stopped = stopped_by(judging, person)
    if stopped is not None:
        return {'skipped': stopped}
    victims = standing_members(judging)
    if not victims:
        return {'skipped': Skipped.NO_TARGET}
    victim = pick_victim(judging, person, victims)
    mark_npc_fight(judging, person.npc, victim)
    attack = choose(person.definition.attacks, judging.dice)
    rolled = roll_attack(judging, person, attack)
    effect = change_sheet(judging, victim, ChangeKind.DAMAGE, attack.harm) if rolled.check.success else None
    outcome = attack_outcome(attack, victim, rolled.check, effect)
    return {**outcome, 'hindrance': round_injuries.hindrance_document(rolled)}
