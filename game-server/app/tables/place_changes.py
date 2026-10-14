# game-server/app/tables/place_changes.py

"""
방장이 캐릭터를 맵의 다른 장소로 옮긴다.

캐릭터가 길을 따라 한 칸씩 가는 것은 선언 행동(move)이다. 방장이 옮기는 것은 이야기가 건너뛴 이동이다.
배를 타고 며칠을 갔다거나, 쓰러진 동료를 업고 갔다거나, 잡혀서 끌려갔다거나.

  - 진행 중인 테이블에서만 한다. 시트(캐릭터)가 있어야 위치가 있다.
  - 살아 있는 캐릭터만 옮긴다. 쓰러진 캐릭터도 살아 있다(업고 간다). 죽은 캐릭터는 쓰러진 곳에 남는다.
  - 아는 장소로만 옮긴다(app/tables/places.py). 방장도 숨긴 것은 모른다. 길로 이어져 있지 않아도 된다.
  - 이미 그 장소에 있으면 아무것도 바꾸지 않고 이벤트도 남기지 않는다.
  - 옮긴 것은 이벤트로 남긴다. 앉은 사람 모두가 스트림으로 본다. 아는 장소만 적히므로 숨긴 것은 새지 않는다.
    새 장소에 서면 그 장소에서 나가는 안개 길을 알게 된다. 그것은 이벤트로 적지 않는다. 테이블을 다시 읽으면 보인다.

AI GM 은 캐릭터를 옮기지 못한다. 서술에서 "성으로 돌아왔다"고 해도 위치는 그대로다.

HTTP 를 모른다. 테이블을 잠그고 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import read_snapshot
from app.events import recorder
from app.events.models import EventType
from app.tables import places
from app.tables.item_grants import living_sheet, require_playing
from app.tables.models import GameTable
from app.tables.service import lock_seated, save
from app.tables.state import require_host


async def move_character(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, user_id: uuid.UUID, place_id: uuid.UUID
) -> GameTable:
    """
    방장이 그 사람의 지금 캐릭터를 아는 장소로 옮긴다.

    방장이 아니면 NotHostError, 진행 중이 아니면 TableConflictError(not_playing), 대상이 없으면 MemberNotFoundError,
    대상의 캐릭터가 죽었으면 TableConflictError(character_dead), 아는 장소가 아니면 TableOptionError(place_id).
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_playing(table)
    member, sheet = living_sheet(table, user_id)
    snapshot = read_snapshot(table.content)
    places.require_known(places.known_map(snapshot, places.knowledge(table)), place_id)
    if sheet.place_id == place_id:
        return await save(session, table)

    previous = sheet.place_id
    places.stand(table, sheet, place_id)
    payload = places.describe_move(snapshot, member, previous, place_id)
    recorder.record(session, table, EventType.CHARACTER_MOVED, actor_id=host_id, payload=payload)
    return await save(session, table)
