# game-server/app/tables/npc_attitudes.py

"""
NPC 의 태도(우호, 중립, 적대)를 바꾸는 일(#474). 바꾸는 것은 엔진뿐이다. 방장도 AI 도 바꾸지 못한다.

처음 태도는 판의 인물에 적은 것이다(app/tables/npcs.py 의 make_npcs). 테이블에서는 엔진의 규칙이 바꾼다.
처음 바꾸는 규칙은 훔치다 들킨 것이다(#457, 들킨 NPC 는 적대가 된다). 그 밖의 까닭은 그 규칙과 함께 더한다.

DB 를 모른다. 이미 읽어 온 NPC 의 상태를 고치고, 이벤트(npc_attitude_changed)에 적을 모양을 돌려준다.
적는 것은 부르는 쪽이다(app/rounds/records.py 의 record_attitude_change).
"""

from app.assets.models import NpcAttitude
from app.tables.models import TableNpc

# 태도를 서술자에게 보일 말. 중립은 적지 않는다(모두가 중립이면 줄만 길어진다)
ATTITUDE_WORDS = {
    NpcAttitude.FRIENDLY: '우호',
    NpcAttitude.HOSTILE: '적대',
}


def change_attitude(npc: TableNpc, attitude: NpcAttitude, reason: str) -> dict | None:
    """
    NPC 의 태도를 바꾼다. 바뀌었으면 이벤트에 적을 모양을, 이미 그 태도였으면 None 을 돌려준다.

    reason 은 바꾼 까닭이다(예: caught_stealing). 이름은 부르는 쪽이 장면의 호칭으로 더한다. 진짜 이름이 새면 안 된다.
    죽은 NPC 도 바꿀 수 있다(되살아나지 않으니 쓰일 일이 없을 뿐이다).
    """
    previous = NpcAttitude(npc.attitude)
    if previous == attitude:
        return None
    npc.attitude = attitude
    return {'entry_id': str(npc.entry_id), 'previous': previous, 'attitude': attitude, 'reason': reason}


def attitude_word(npc: TableNpc) -> str | None:
    """서술자에게 보일 태도의 말. 중립이면 None 이다."""
    return ATTITUDE_WORDS.get(NpcAttitude(npc.attitude))
