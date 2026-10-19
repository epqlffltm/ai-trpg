# trpg-server/app/rounds/downed_strikes.py

"""
쓰러진 캐릭터를 치는 일(#369). 몬스터의 차례(app/rounds/monster_attacks.py)와 싸우는 NPC 의 차례
(app/rounds/npc_attacks.py)가 함께 쓴다.

쓰러진 쪽이 서 있는 쪽보다 안전하면 안 된다. 일행이 모두 쓰러져도 전투가 멈추지 않고 마무리된다.
  - 대상의 후보(can_be_struck): 서 있는 캐릭터와, 라운드를 닫기 시작할 때 이미 쓰러져 있던(죽지 않은) 캐릭터.
    이번 라운드에 앞 차례에서 쓰러진 캐릭터는 이번 라운드에는 후보가 아니다. 동료가 일으킬 틈이다.
    규칙에 죽음의 굴림이 없으면(death_save 가 None) 쓰러진 캐릭터는 후보가 아니다. 죽일 길이 없는 판이다.
    고비를 넘긴 캐릭터도 쓰러진 채이므로 후보다. 서 있는 캐릭터와 같은 주사위로 고른다(가중치 없음).
  - 판정은 서 있는 대상과 같다. 맞히면 피해는 없고 죽음의 굴림 실패가 쌓인다(app/engine/death.py 의 add_failures).
    큰 타격으로 쓰러진 캐릭터면 더 쌓인다. 실패가 규칙의 수에 닿으면 그 자리에서 죽는다. 빗나가면 아무 일도 없다.

결과는 차례의 outcome 의 downed_strike 다. 쓰러진 대상을 쳤을 때만 있다.
DB 를 모른다. 시트를 고친다. 저장하지는 않는다.
"""

from dataclasses import asdict

from app.engine import death
from app.rounds.effects import Judging
from app.tables import sheets
from app.tables.models import TableMember


def strikes_downed(judging: Judging) -> bool:
    """이 판에서 쓰러진 캐릭터를 칠 수 있는가. 규칙에 죽음의 굴림이 있어야 한다."""
    return judging.ruleset.death_save is not None


def can_be_struck(judging: Judging, member: TableMember) -> bool:
    """
    이 캐릭터가 공격의 대상이 될 수 있는가. 장소는 보지 않는다(부르는 쪽이 본다).

    죽지 않았고, 서 있거나 라운드를 닫기 시작할 때부터 쓰러져 있었다(규칙에 죽음의 굴림이 있을 때만).
    """
    if member.sheet is None or sheets.is_dead(member):
        return False
    if not sheets.is_downed_alive(member):
        return True
    return member.user_id in judging.downed_at_start and strikes_downed(judging)


def strike_downed(judging: Judging, victim: TableMember, hit: bool) -> dict:
    """
    쓰러진 캐릭터를 친 결과. 맞았으면 죽음의 굴림 실패를 쌓고, 닿으면 죽었다고 적는다. 결과의 문서를 돌려준다.

    added 는 이번에 쌓인 실패(빗나가면 0), failures 는 그 뒤의 실패, limit 는 죽는 수, fate 는 그 뒤의 갈림길이다.
    후보를 고를 때 규칙에 죽음의 굴림이 있는 것을 봤다(can_be_struck).
    """
    rule = judging.ruleset.death_save
    sheet = victim.sheet
    count = death.struck_failures(sheet.downed_by_big_hit) if hit else 0
    struck = death.add_failures(rule, sheet.death_successes, sheet.death_failures, count)
    sheet.death_failures = struck.failures
    if struck.fate == death.Fate.DEAD:
        sheets.mark_dead(sheet)
    return asdict(struck)
