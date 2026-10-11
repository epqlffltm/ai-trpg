# game-server/app/rounds/naming.py

"""
지목. 플레이어가 인물의 진짜 이름을 맞히는 것을 판단하는 작은 함수들.

장면에서 인물은 호칭으로 불린다(app/rounds/cast.py 의 scene_label). 진짜 이름은 로어북에만 있고 AI 만 읽는다.
플레이어가 이름을 짚으면 서버가 정답과 견준다. 정답은 제작자가 인물 항목마다 적는다(true_names).
적지 않았으면 항목의 이름 하나다. 견줄 때는 대소문자, 빈칸, 전각과 반각의 차이를 가리지 않는다.

맞히면 그 테이블에서 그 인물은 진짜 이름으로 불린다(TableNpc.named_round). 틀리면 아무 일도 없다.
맞은 것은 이름뿐이다. "범인은 비올레타다"의 "범인"이 맞는지는 엔진이 정하지 않는다.

여기의 함수는 DB 를 모른다. 판의 인물 항목과 짚은 이름을 받아 본다.
판정(judge_naming)은 닫히는 라운드에서 한 번 한다(app/rounds/judging.py). 주사위를 굴리지 않는다.
맞으면 이미 읽어 온 NPC 의 상태에 맞힌 라운드를 적는다. 저장은 부른 쪽이 한다.
"""

import unicodedata
from collections.abc import Iterable

from app.assets.scenarios.snapshot import EntrySnapshot
from app.engine.action import NameAction
from app.rounds.cast import find_cast_member, is_named
from app.rounds.effects import Judging
from app.tables.models import TableNpc


def normalize(name: str) -> str:
    """견주기 위한 모양. 전각과 반각을 맞추고(NFKC), 대소문자를 가리지 않고, 빈칸을 모두 뺀다."""
    return ''.join(unicodedata.normalize('NFKC', name).casefold().split())


def answers_of(entry: EntrySnapshot) -> list[str]:
    """이 인물을 지목할 때 맞다고 받는 이름들. 제작자가 적지 않았으면 항목의 이름 하나다."""
    return list(entry.true_names) or [entry.name]


def matches(entry: EntrySnapshot, guess: str) -> bool:
    """짚은 이름이 이 인물의 정답 중 하나인가."""
    wanted = normalize(guess)
    return any(normalize(answer) == wanted for answer in answers_of(entry))


def find_named(entries: Iterable[EntrySnapshot], guess: str) -> EntrySnapshot | None:
    """짚은 이름이 정답인 인물. 여럿이면 판의 차례에서 앞의 것이다. 없으면 None."""
    return next((entry for entry in entries if matches(entry, guess)), None)


def find_target(people: Iterable[EntrySnapshot], npcs: dict, action: NameAction) -> EntrySnapshot | None:
    """
    지목이 맞힌 인물. 틀렸으면 None.

    겨눈 인물이 있으면 그 인물의 정답과만 견준다. 없으면 상태가 있는 인물 모두에서 찾는다.
    상태가 없는 인물(이 기능이 생기기 전에 시작한 테이블)은 맞힐 수 없다. 맞혀도 적어 둘 곳이 없다.
    """
    known = [entry for entry in people if entry.id in npcs]
    if action.npc is None:
        return find_named(known, action.name)
    entry = next((entry for entry in known if entry.id == action.npc), None)
    return entry if entry is not None and matches(entry, action.name) else None


def mark_named(npc: TableNpc, round_number: int) -> bool:
    """맞힌 라운드를 적는다. 이미 드러난 인물이면 그대로 둔다. 새로 드러났는지를 돌려준다."""
    if is_named(npc):
        return False
    npc.named_round = round_number
    return True


def judge_naming(judging: Judging, action: NameAction) -> dict:
    """
    지목을 판정하고 그 결과를 정한다. 맞으면 그 인물의 진짜 이름이 이 테이블에서 드러난다.

    결과의 label 은 이번 장면에서 그 인물을 부르던 이름이다. 겨눴거나, 맞힌 인물이 장면에 나왔을 때만 있다.
    진짜 이름(name)은 맞았을 때만 적는다. 틀린 결과에는 정답의 흔적이 없어야 한다.
    """
    npcs = {npc.entry_id: npc for npc in judging.npcs}
    found = find_target(judging.people, npcs, action)
    target = action.npc if action.npc is not None else (found.id if found is not None else None)
    member = find_cast_member(judging.cast, target) if target is not None else None
    return {
        'naming': {
            'guess': action.name,
            'correct': found is not None,
            'entry_id': str(target) if target is not None else None,
            'name': found.name if found is not None else None,
            'label': member.name if member is not None else None,
            'newly': found is not None and mark_named(npcs[found.id], judging.round_number),
        }
    }
