# game-server/app/rounds/narration_request.py

"""
DB 에 적힌 라운드를 서술자에게 줄 모양(app/rounds/narrator.py)으로 바꾼다. 그리고 그 모양을 저장하고 다시 읽는다.

서술자에게 주는 것은 셋이다.
  - 이번 라운드에 각자 한 일(moves). 닫기 시작할 때 만들어 라운드에 굳혀 둔다(dump_moves, read_moves).
  - 이야기의 바탕(story). 판의 복사본에서 꺼낸다. 판은 고치지 않으므로 굳힐 필요가 없다.
  - 지난 라운드들(history). 닫힌 라운드는 바뀌지 않으므로 굳힐 필요가 없다.
    한 말은 그 라운드에 굳혀 둔 각자 한 일에서 읽는다(to_past). 서술자가 그때 받은 것과 같은 사람들이다.

각자 한 일을 굳히는 이유. 서술은 저장한 뒤에 따로 돈다(app/rounds/closing.py).
그 사이에 누가 나가거나, 서술이 실패해서 다시 맡기면, 지금의 테이블로 다시 만든 것은 닫힐 때와 다르다.
나간 사람의 판정과 HP 의 변화는 기록에 있는데 장면에서는 빠진다. 굳혀 두면 몇 번을 맡겨도 같은 것을 받는다.

여기의 함수는 DB 도 테이블도 모른다. 이미 읽어 온 라운드, 선언, 판의 복사본을 받아 모양만 바꾼다.
"""

import uuid
from dataclasses import asdict

from pydantic import TypeAdapter

from app.assets.scenarios.snapshot import Snapshot
from app.engine.check import find_ability, find_difficulty
from app.engine.injury import known_injuries
from app.engine.ruleset import Ruleset
from app.rounds.models import Declaration, Round
from app.rounds.narrator import DeathSaveNote, Impact, Move, NpcImpact, PastRound, StoryContext, Verdict

# 굳혀 둔 행동들을 읽는 법. 모양이 틀리면 ValidationError 를 낸다. 우리가 쓴 문서이니 틀렸으면 버그다
MOVES = TypeAdapter(list[Move])


def find_death_save(round_: Round, user_id: uuid.UUID) -> DeathSaveNote | None:
    """라운드에 적힌 죽음의 굴림 중에서 이 사람의 것을 서술자에게 줄 모양으로 찾는다. 없으면 None."""
    found = next((save for save in round_.death_saves if save['user_id'] == str(user_id)), None)
    if found is None:
        return None
    return DeathSaveNote(
        roll=found['roll'],
        target=found['target'],
        success=found['success'],
        successes=found['successes'],
        failures=found['failures'],
        fate=found['fate'],
    )


def new_injury_name(effect: dict) -> str | None:
    """HP 의 변화를 적은 문서에서 새로 입은 부상의 이름. 표를 굴리지 않았거나 부상이 없었으면 None."""
    injury_roll = effect.get('injury_roll')
    return injury_roll['name'] if injury_roll else None


def to_impact(effect: dict | None) -> Impact | None:
    """선언에 적힌 HP 의 변화를 서술자에게 줄 모양으로 바꾼다. 변화가 없었으면 None."""
    if effect is None:
        return None
    return Impact(
        kind=effect['kind'],
        character_name=effect['character_name'],
        amount=effect['amount'],
        hp=effect['after'],
        max_hp=effect['max_hp'],
        downed=effect['downed'],
        injury=new_injury_name(effect),
    )


def to_npc_impact(effect: dict | None) -> NpcImpact | None:
    """
    선언에 적힌 NPC 의 HP 의 변화를 서술자에게 줄 모양으로 바꾼다. 변화가 없었으면 None.

    몸 상태는 바뀐 뒤의 것이다. 바꿀 때 적어 둔 것을 읽는다(app/rounds/service.py 의 change_cast_member).
    """
    if effect is None:
        return None
    return NpcImpact(
        kind=effect['kind'],
        name=effect['name'],
        amount=effect['amount'],
        condition=effect['condition'],
        injury=new_injury_name(effect),
    )


def to_verdict(ruleset: Ruleset, declaration: Declaration) -> Verdict:
    """
    선언에 적힌 행동과 결과를 서술자에게 줄 모양으로 바꾼다. key 를 규칙에 적힌 이름으로 바꾼다.

    결과가 적힌 선언에만 쓴다.
    """
    ability = find_ability(ruleset, declaration.action['ability'])
    difficulty = find_difficulty(ruleset, declaration.action['difficulty'])
    outcome = declaration.outcome
    return Verdict(
        ability=ability.name,
        difficulty=difficulty.name,
        roll=outcome['roll'],
        modifier=outcome['modifier'],
        total=outcome['total'],
        target=outcome['target'],
        success=outcome['success'],
        impact=to_impact(outcome.get('effect')),
        npc_impact=to_npc_impact(outcome.get('npc_effect')),
        hindrances=hindrance_names(ruleset, outcome.get('hindrance')),
        aimed=aimed_name(ruleset, outcome.get('called_shot')),
    )


def aimed_name(ruleset: Ruleset, called_shot: dict | None) -> str | None:
    """노린 부상의 이름. 규칙에 적힌 이름이다. 노려 치지 않았으면 None."""
    if called_shot is None:
        return None
    found = known_injuries(ruleset, [called_shot['aim']])
    return found[0].name if found else None


def hindrance_names(ruleset: Ruleset, hindrance: dict | None) -> list[str]:
    """판정에 영향을 준 부상들의 이름. 규칙에 적힌 이름이다. 영향이 없었으면 비어 있다."""
    if hindrance is None:
        return []
    return [injury.name for injury in known_injuries(ruleset, hindrance['injuries'])]


def to_story(snapshot: Snapshot) -> StoryContext:
    """
    판의 복사본에서 이야기의 바탕을 꺼낸다. 서술자에게만 준다.

    룰북의 진행 지침과 세계관의 GM 메모가 들어간다. 이것들은 AI 가 읽으라고 쓴 글이다. 플레이어에게 내보내지 않는다.
    세계관이 없는 시나리오면 설정과 GM 메모는 빈 글이다. 로어북은 넣지 않는다(검색 단계의 일).
    """
    world = snapshot.world
    return StoryContext(
        title=snapshot.title,
        rating=snapshot.rating,
        guide=snapshot.rulebook.gm_guide,
        setting=world.setting if world else '',
        gm_notes=world.gm_notes if world else '',
    )


def said_in_moves(moves: list[dict]) -> list[tuple[str, bool | None]]:
    """
    굳혀 둔 각자 한 일에서 한 말들을 꺼낸다. 하나하나가 ("캐릭터 이름: 글", 판정이 성공했는가)다.

    선언을 내지 않은 사람(글이 없음)은 뺀다. 판정이 없던 선언은 성공 여부가 None 이다.
    문서를 통째로 검사하지 않고(read_moves) 필요한 칸만 읽는다. 오래된 라운드는 나중에 생긴 칸이 없을 수 있다.
    지난 라운드를 읽다가 서술이 멈추면 안 된다.
    """
    return [
        (f'{move["character_name"]}: {move["content"]}', (move.get('verdict') or {}).get('success'))
        for move in moves
        if move.get('content') is not None
    ]


def said_in_declarations(declarations: list[Declaration]) -> list[tuple[str, bool | None]]:
    """
    선언들에서 한 말들을 꺼낸다. 굳혀 둔 것이 없는 옛 라운드에만 쓴다.

    선언에 적어 둔 캐릭터 이름을 쓴다. 판정의 결과가 적혀 있으면 성공 여부를 읽는다.
    """
    return [
        (f'{declaration.character_name}: {declaration.content}', (declaration.outcome or {}).get('success'))
        for declaration in declarations
    ]


def to_past(round_: Round) -> PastRound:
    """
    지난 라운드를 서술자에게 줄 모양으로 바꾼다. 그때의 장면과, 한 말마다 "캐릭터 이름: 글" 한 줄.

    한 말은 닫기 시작할 때 굳혀 둔 각자 한 일(round_.moves)에서 읽는다. 그 라운드의 서술자가 받은 것과 같다.
      - 마감 전에 나간 사람의 선언은 판정도 서술도 받지 않았다. 굳혀 둔 것에 없으므로 여기에도 없다.
        선언 자체는 라운드의 기록에 남는다(GET /rounds/{number}). 서술자에게 주는 지난 일에서만 빠진다.
      - 마감 뒤에 나간 사람의 것은 굳혀 둔 것에 있다. 지금 앉은 사람으로 거르지 않으므로 그대로 남는다.
    굳혀 둔 것이 없는 라운드(그 칸이 생기기 전에 닫힌 옛 라운드, 아직 선언을 받는 라운드)는 선언을 읽는다.
    옛 라운드는 누가 마감 전에 나갔는지 알 수 없어 낸 선언이 모두 들어간다.
    """
    said = said_in_declarations(round_.declarations) if round_.moves is None else said_in_moves(round_.moves)
    return PastRound(
        number=round_.number,
        scene=round_.scene,
        lines=[line for line, _ in said],
        successes=[success for _, success in said],
    )


def dump_moves(moves: list[Move]) -> list[dict]:
    """각자 한 일을 라운드에 굳혀 둘 모양(JSON)으로 바꾼다."""
    return [asdict(move) for move in moves]


def read_moves(data: list[dict]) -> list[Move]:
    """라운드에 굳혀 둔 것을 각자 한 일로 다시 읽는다. 모양이 틀리면 ValidationError."""
    return MOVES.validate_python(data)
