# trpg-server/app/rounds/reverting.py

"""
방장이 바로 앞 라운드를 되돌리는 규칙(#288, 2026-11-03 유저 결정). DB 를 모른다. 이미 읽어 온 것을 받는다.

되돌리기는 이렇게 한다(app/rounds/service.py 의 revert_round).
  1. 라운드를 닫기 시작할 때 그 직전의 게임 상태를 찍어 둔다(app/rounds/snapshots.py). 테이블마다 마지막 하나다.
  2. 방장이 되돌리면 그 상태로 덮는다. 판정, HP, 부상, 퀘스트, 몬스터, 맵 … 닫기가 바꾼 것이 모두 돌아간다.
  3. 앞 라운드(N)는 지우지 않고 되돌렸다고 적는다(reverted_at). 기록이다.
  4. 지금 열린 라운드(N+1)가 N 의 번호와 장면을 받아 다시 열린 N 이 된다. N 의 선언(글과 행동)을 옮겨 적는다.
     고칠 사람만 고치고, 모두 내면 다시 닫힌다. 주사위는 새로 굴린다.
  5. round_reverted 를 적는다. 닫힘의 묶음은 지우지 않고, 읽는 쪽이 그 묶음을 빼고 본다.

정한 것(2026-11-03)
  - 서술 값은 돌려주지 않는다. 모델의 원가는 이미 나갔다. 다시 닫으면 다시 받는다. 받는 것은 N+1 을 열 때 걸어 둔
    홀드다. 다시 연 라운드가 그 라운드의 행이라서 결제 서버를 새로 부르지 않는다.
  - 되돌린 선언은 남기고 고칠 수 있다.
  - 횟수에 제한이 없다. 바로 앞 라운드 하나만 되돌린다. 다시 닫으면 그것이 새 "바로 앞"이다.

되돌릴 수 있는 때(blocker)
  - 방장이다. 지금 라운드가 선언을 받는 중이다. 첫 라운드가 아니다.
  - 지금 라운드에 아무도 선언하지 않았다.
  - 지금 라운드가 열린 뒤에 쪽지와 설정 바꾸기(AFTER_OPENED) 말고 아무 일도 없었다. 장비를 바꾸거나 들고 나면
    그 일을 닫기 직전의 상태로 덮게 된다. 설정은 찍지 않는 칸이라 덮이지 않는다.
  - 찍어 둔 것이 앞 라운드의 것이고 지금의 표 모양과 맞는다.
테이블을 잠그고 본다. 지금 라운드가 선언을 받는 중이면 돌고 있는 서술 작업이 없다(앞 라운드는 닫혔다).
"""

from datetime import datetime

from app.events.models import EventType
from app.rounds.errors import Conflict
from app.rounds.models import Declaration, Round, RoundSnapshot, RoundStatus
from app.rounds.snapshots import fits

# 지금 라운드가 열린 뒤에 있어도 되돌릴 수 있는 일들. 게임의 상태를 바꾸지 않는다(찍지 않는 칸만 바꾼다)
AFTER_OPENED: frozenset[str] = frozenset(
    {
        EventType.WHISPER_SENT,
        EventType.DICE_ROLLED,
        EventType.HOST_CHANGED,
        EventType.NARRATION_STYLE_CHANGED,
        EventType.ROUND_TIME_LIMIT_CHANGED,
        EventType.NARRATION_TIER_CHANGED,
        EventType.NARRATION_MODEL_CHANGED,
        EventType.CREDIT_WAIT_CHANGED,
        EventType.WHISPER_NOTICE_CHANGED,
        EventType.REFERENCES_CHANGED,
        EventType.FRIENDLY_FIRE_CHANGED,
        EventType.FRIENDLY_FIRE_CONSENT_CHANGED,
        EventType.NARRATION_CREDITS_SHORT,
        EventType.NARRATION_MODEL_NOT_FOR_SALE,
        EventType.NARRATION_MODEL_RETIRING,
        EventType.NARRATION_MODEL_REPLACED,
        EventType.NARRATION_MODEL_UNAVAILABLE,
    }
)


def blocker(
    current: Round,
    previous: Round | None,
    snapshot: RoundSnapshot | None,
    types_after: list[str],
) -> Conflict | None:
    """
    되돌릴 수 없는 까닭. 되돌릴 수 있으면 None.

    current 는 지금 라운드, previous 는 그 앞 라운드(첫 라운드면 None)다. types_after 는 지금 라운드가 열린 뒤의
    이벤트의 종류들이다.
    """
    if current.status != RoundStatus.OPEN:
        return Conflict.ROUND_CLOSING
    if previous is None or snapshot is None or snapshot.round_id != previous.id or not fits(snapshot.state):
        return Conflict.NOTHING_TO_REVERT
    if current.declarations or any(type_ not in AFTER_OPENED for type_ in types_after):
        return Conflict.REVERT_BLOCKED
    return None


def copied_declarations(previous: Round) -> list[Declaration]:
    """앞 라운드의 선언을 다시 연 라운드에 옮겨 적을 것. 글과 행동만 옮긴다. 결과는 다시 닫을 때 다시 굴린다."""
    return [
        Declaration(
            user_id=declaration.user_id,
            character_name=declaration.character_name,
            content=declaration.content,
            action=declaration.action,
        )
        for declaration in previous.declarations
    ]


def reopen(current: Round, previous: Round, deadline: datetime | None) -> None:
    """
    지금 라운드를 앞 라운드로 다시 연다. 번호, 장면, 들어온 캐릭터, 선언을 받는다. 마감은 지금부터 다시 센다.
    차례대로 진행하는 테이블(#287)이면 바퀴와 차례의 주인도 받는다(남은 차례는 찍어 둔 테이블의 것으로 돌아간다).

    서술 모델과 단계, 알린 값은 지금 라운드의 것 그대로다. 그 값으로 걸어 둔 홀드로 다시 닫는 서술 값을 받는다.
    앞 라운드를 먼저 되돌렸다고 적고 DB 에 보낸 뒤에 부른다(번호의 유일 조건, uq_table_rounds_number).
    """
    current.number = previous.number
    current.cycle = previous.cycle
    current.actor_id = previous.actor_id
    current.scene = previous.scene
    current.arrivals = list(previous.arrivals)
    current.deadline_at = deadline
    current.declarations = copied_declarations(previous)


def reverted_payload(number: int, group: object, deadline: datetime | None, clock: dict) -> dict:
    """round_reverted 의 내용. 다시 연 번호, 되돌린 닫힘의 묶음, 다시 센 마감, 돌아간 게임 안의 시각이다."""
    return {
        'number': number,
        'group': str(group),
        'deadline_at': deadline.isoformat() if deadline is not None else None,
        'clock': clock,
    }
