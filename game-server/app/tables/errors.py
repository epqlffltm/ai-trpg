# game-server/app/tables/errors.py

"""
테이블의 일이 거절되는 까닭들. 서비스가 던지고, 라우터의 처리기가 HTTP 응답으로 바꾼다(app/main.py 에 등록).

HTTP 상태 코드는 여기서 정하지 않는다. 무엇이 틀렸는지만 적는다.
  - TableNotFoundError: 그런 테이블이 없거나 앉지 않았다(404). 앉지 않은 사람에게는 "없는 테이블"이다.
  - MemberNotFoundError: 그 사람은 이 테이블에 앉아 있지 않다(404).
  - NotHostError: 방장만 하는 일이다(403).
  - WrongPasswordError: 테이블의 비밀번호가 틀렸다(403).
  - 성인용 테이블의 거절(403)은 등급을 가르는 곳의 것(app/assets/ratings.py 의 AdultContentRequiredError)을 쓴다.
  - TableConflictError: 요청은 맞지만 테이블의 지금 상태와 부딪힌다. 까닭은 Conflict 다(409).
  - TableOptionError: 고를 수 없는 것을 골랐다(422).
"""

import enum


class TableNotFoundError(Exception):
    """그런 테이블이 없다. 앉지 않은 사람이 찾은 경우, 초대 코드가 틀린 경우도 이 예외다."""


class MemberNotFoundError(Exception):
    """그 사람은 이 테이블에 앉아 있지 않다."""


class NotHostError(Exception):
    """방장만 할 수 있는 일을 방장이 아닌 참가자가 하려 했다."""


class WrongPasswordError(Exception):
    """테이블의 비밀번호가 틀렸다. 비밀번호가 걸린 테이블에 비밀번호 없이 들어오려 한 경우도 이 예외다."""


class Conflict(enum.StrEnum):
    """요청은 맞지만 테이블의 지금 상태와 부딪히는 이유."""

    # 자리가 다 찼다
    TABLE_FULL = 'table_full'
    # 모집 중이 아니다. 들어오기, 캐릭터 정하기, 시작은 모집 중에만 된다
    NOT_RECRUITING = 'not_recruiting'
    # 테이블이 이미 끝났다
    ALREADY_ENDED = 'already_ended'
    # 이미 앉아 있다
    ALREADY_SEATED = 'already_seated'
    # 다른 사람이 그 프리젠을 가져갔다
    PREGEN_TAKEN = 'pregen_taken'
    # 이 테이블에서 허용하지 않는 방식으로 캐릭터를 정하려 했다
    CHARACTER_MODE_NOT_ALLOWED = 'character_mode_not_allowed'
    # 캐릭터를 만들지 않은 사람이 있다. 받을 시트가 없는 사람이 있는 경우도 이 이유다
    CHARACTERS_MISSING = 'characters_missing'
    # 프리젠만 허용한 테이블인데 정원이 프리젠의 수보다 많다
    PREGENS_TOO_FEW = 'pregens_too_few'
    # 방장은 자신을 내보낼 수 없다. 나가기를 쓴다
    CANNOT_KICK_SELF = 'cannot_kick_self'
    # 이 테이블에서 이미 굴렸다. 한 사람은 한 번 굴린다. 방장이 "한 번 더"를 줘야 다시 굴린다
    ALREADY_ROLLED = 'already_rolled'
    # 아직 굴리지 않았다. 굴린 점수가 있어야 능력치에 놓을 수 있고, "한 번 더"를 받을 수 있다
    NOT_ROLLED = 'not_rolled'
    # 이 테이블에서는 다시 굴리게 해 줄 수 없다. 시나리오의 제작자가 허락하지 않았다
    REROLL_NOT_ALLOWED = 'reroll_not_allowed'
    # 이미 "한 번 더"를 줬고, 그 사람이 아직 쓰지 않았다
    REROLL_ALREADY_GRANTED = 'reroll_already_granted'
    # 진행 중인 테이블이 아니다. 캐릭터를 보내는 것은 진행 중에만 된다
    NOT_PLAYING = 'not_playing'
    # 캐릭터가 쓰러져 있지 않다. 멀쩡한 캐릭터는 보낼 수 없다
    CHARACTER_NOT_DOWNED = 'character_not_downed'
    # 캐릭터가 이미 죽었다
    CHARACTER_DEAD = 'character_dead'
    # 캐릭터가 살아 있다. 진행 중에는 캐릭터가 죽은 사람만 새 캐릭터를 정한다
    CHARACTER_ALIVE = 'character_alive'
    # 한 가지 물건을 가질 수 있는 개수(99)를 넘는다
    TOO_MANY_ITEMS = 'too_many_items'
    # 가진 것보다 많이 빼려 했다. 없는 물건을 빼려 한 것도 이 이유다
    NOT_ENOUGH_ITEMS = 'not_enough_items'
    # 이미 끝난(성공, 실패) 퀘스트다. 끝난 것은 되돌리지 않는다
    QUEST_FINISHED = 'quest_finished'
    # 퀘스트를 사람이 드러내려(진행 중으로 바꾸려) 했다. 드러나는 것은 시나리오의 조건을 보고 엔진이 정한다
    QUEST_REVEAL_BY_ENGINE = 'quest_reveal_by_engine'
    # 시작한 테이블의 서술 모델을 바꾸려 했다. 지금 모델을 쓸 수 있으면 시작한 뒤에는 고정이다
    NARRATION_MODEL_LOCKED = 'narration_model_locked'
    # 퀘스트를 사람이 성공으로 바꾸려 했다. 성공은 시나리오의 조건을 보고 엔진이 정한다(app/rounds/quest_goals.py)
    QUEST_SUCCESS_BY_ENGINE = 'quest_success_by_engine'
    # 판의 작가 글(진행 지침, 세계관, GM 메모)이 서술의 입력 예산을 넘어 시작할 수 없다(app/rounds/budget.py)
    STORY_TOO_LONG = 'story_too_long'


class TableConflictError(Exception):
    """테이블의 지금 상태와 부딪힌다. reason 이 이유다."""

    def __init__(self, reason: Conflict) -> None:
        super().__init__(reason)
        self.reason = reason


class TableOptionError(Exception):
    """
    고른 것이 판에 없다. 없는 스타팅이나 없는 프리젠을 골랐거나, 판이 허용하지 않는 캐릭터 방식을 골랐다.

    직접 정한 능력치가 이 테이블의 규칙에 맞지 않을 때도 이 오류다.
    field 는 입력의 어느 칸이 틀렸는지다(opening_index, pregen_index, character_modes, abilities).
    """

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field
