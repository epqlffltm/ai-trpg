# trpg-server/app/rounds/errors.py

"""
라운드의 일이 거절되는 까닭들. 서비스가 던지고, 라우터의 처리기가 HTTP 응답으로 바꾼다(app/rounds/router.py).

HTTP 상태 코드는 여기서 정하지 않는다. 무엇이 틀렸는지만 적는다.
  - RoundNotFoundError: 그런 번호의 라운드가 없다(404).
  - RoundConflictError: 요청은 맞지만 테이블의 지금 상태와 부딪힌다. 까닭은 Conflict 다(409).
  - ActionNotInRulesError: 행동이 테이블의 규칙에 없는 것을 가리킨다(422).
  - ActionTargetError: 행동의 대상을 겨눌 수 없다(422).
"""

import enum


class RoundNotFoundError(Exception):
    """그런 번호의 라운드가 없다."""


class Conflict(enum.StrEnum):
    """요청은 맞지만 테이블의 지금 상태와 부딪히는 이유."""

    # 테이블이 아직 시작하지 않았다. 라운드가 하나도 없다
    NOT_STARTED = 'not_started'
    # 테이블이 진행 중이 아니다. 선언과 닫기는 진행 중에만 된다
    NOT_PLAYING = 'not_playing'
    # 라운드가 닫는 중이다. 선언을 마감했고 GM 이 서술하고 있다. 끝나면 다음 라운드가 열린다
    ROUND_CLOSING = 'round_closing'
    # 캐릭터가 쓰러져 있다. 행동을 붙일 수 없다. 글만 낼 수 있다
    CHARACTER_DOWNED = 'character_downed'
    # 캐릭터가 죽었다. 선언을 낼 수 없다. 새 캐릭터가 있어야 한다
    CHARACTER_DEAD = 'character_dead'
    # 이 라운드에 새로 들어온 캐릭터다. 다음 라운드부터 선언을 낸다
    CHARACTER_ARRIVING = 'character_arriving'
    # 행동이 겨눈 NPC 가 이미 죽었다
    NPC_DEAD = 'npc_dead'
    # 행동이 겨눈 몬스터가 이미 죽었다(부서졌다)
    MONSTER_DEAD = 'monster_dead'
    # 캐릭터가 입은 부상 때문에 행동하지 못한다(기절 같은 것). 글만 낼 수 있다
    CHARACTER_INCAPACITATED = 'character_incapacitated'
    # 노려 친 부상을 대상이 이미 입고 있다(이미 잃은 눈)
    ALREADY_INJURED = 'already_injured'
    # 치료하려는 부상을 대상이 입고 있지 않다
    NOT_INJURED = 'not_injured'
    # 치료하려는 캐릭터가 이미 죽었다
    PATIENT_DEAD = 'patient_dead'
    # 지목한 인물의 진짜 이름이 이미 드러났다
    ALREADY_NAMED = 'already_named'
    # 쓰거나 건네려는 물건을 그만큼 가지고 있지 않다
    ITEM_NOT_HELD = 'item_not_held'
    # 물건을 받을 캐릭터가 이미 죽었다
    RECIPIENT_DEAD = 'recipient_dead'
    # 물건을 받을 캐릭터가 그 물건을 더 가질 수 없다(한 가지 99 개)
    RECIPIENT_FULL = 'recipient_full'
    # 맵에서 가거나 찾으려는데 캐릭터가 맵에 서 있지 않다. 맵이 없는 판이거나, 맵이 생기기 전에 시작한 테이블이다
    NOT_ON_MAP = 'not_on_map'
    # 빼앗으려는 대상이 쓰러지지 않았다(살아 있다). 그때는 훔치기다
    TARGET_NOT_DOWN = 'target_not_down'


class RoundConflictError(Exception):
    """테이블의 지금 상태와 부딪힌다. reason 이 이유다."""

    def __init__(self, reason: Conflict) -> None:
        super().__init__(reason)
        self.reason = reason


class ActionNotInRulesError(Exception):
    """
    선언에 붙은 행동이 이 테이블의 규칙에 없는 것을 가리킨다.

    field 는 행동의 어느 칸이 틀렸는지다(ability, difficulty, risk, recover, harm, aim, injury, item, target).
    """

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


class ActionTargetError(Exception):
    """
    선언에 붙은 행동의 대상이 겨눌 수 없는 것이다.

    field 는 행동의 어느 칸인지다. target 이면 이 테이블에 앉은 사람이 아니고, npc 면 이번 장면에 나온 인물이 아니다.
    place 면 지금 장소에서 아는 길로 이어진 장소가 아니다. item 이면 지금 장소에 보이게 놓인 물건이 아니다(줍기).
    carry 면 같은 장소에 쓰러져 있는(죽지 않은) 다른 사람이 아니다(업고 가기).
    """

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field
