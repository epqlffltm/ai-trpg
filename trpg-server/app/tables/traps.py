# trpg-server/app/tables/traps.py

"""
테이블의 장소에 놓인 덫(#806)을 다루는 규칙. 어디에 무엇이 놓였고, 무엇이 아직 터지지 않았는가.

  - 놓기: 캐릭터가 가진 덫 물건 하나를 서 있는 장소에 숨겨 놓는다(app/rounds/trap_actions.py).
  - 놓인 덫은 숨긴 채다. 놓은 사람도 일행도 따로 알지 못한다. 그 장소에 들어오는 쪽이 터뜨린다.
  - 찾기 행동으로 찾으면(found) 테이블 모두가 안다(#806 ①-b). 아는 덫은 캐릭터가 밟지 않는다.
  - 터지면(sprung) 또는 해제해 거두면(disarmed) 끝난다. 끝난 덫은 지우지 않는다. 무엇이 있었는지 남긴다.

DB 를 모른다. 이미 읽어 온 테이블의 덫(GameTable.traps)을 고친다. 저장은 부르는 쪽이 한다.
"""

import uuid
from datetime import UTC, datetime

from app.tables.models import GameTable, TableTrap, TrapEnd


def lay(
    table: GameTable, place_id: uuid.UUID, entry_id: uuid.UUID, set_by: uuid.UUID | None, round_number: int
) -> TableTrap:
    """
    그 장소에 덫 하나를 놓는다. 놓은 덫을 돌려준다. 놓은 차례의 뒤부터 들어오는 쪽에게 터진다.

    id 와 놓은 시각은 여기서 정한다. 저장하기 전에 같은 라운드에 터지면 결과에 id 가 적히고,
    한 라운드에 여럿을 놓아도 다시 읽을 때 놓은 순서(created_at)가 그대로다(DB 의 now() 는 트랜잭션마다 하나다).
    """
    trap = TableTrap(
        id=uuid.uuid4(),
        table_id=table.id,
        place_id=place_id,
        entry_id=entry_id,
        set_by=set_by,
        round_number=round_number,
        created_at=datetime.now(UTC),
    )
    table.traps.append(trap)
    return trap


def is_armed(trap: TableTrap) -> bool:
    """아직 놓여 있는가. 터지거나 거두지 않았다."""
    return trap.ended_at is None


def is_known(trap: TableTrap) -> bool:
    """테이블이 찾아낸 덫인가(#806 ①-b)."""
    return trap.found_at is not None


def armed_at(table: GameTable, place_id: uuid.UUID) -> list[TableTrap]:
    """그 장소에 아직 놓여 있는 덫들. 놓은 순서다."""
    return [trap for trap in table.traps if trap.place_id == place_id and is_armed(trap)]


def hidden_at(table: GameTable, place_id: uuid.UUID) -> list[TableTrap]:
    """그 장소에 놓여 있고 아직 아무도 찾지 못한 덫들. 놓은 순서다. 들어온 캐릭터가 터뜨리고, 찾기가 찾는다."""
    return [trap for trap in armed_at(table, place_id) if not is_known(trap)]


def known_at(table: GameTable, place_id: uuid.UUID) -> list[TableTrap]:
    """그 장소에 놓여 있고 테이블이 찾아낸 덫들. 놓은 순서다. 해제할 수 있고, 맵에 보인다."""
    return [trap for trap in armed_at(table, place_id) if is_known(trap)]


def find_trap(table: GameTable, trap_id: uuid.UUID) -> TableTrap | None:
    """이 테이블의 덫 하나. 끝난 것도 돌려준다. 없으면 None."""
    return next((trap for trap in table.traps if trap.id == trap_id), None)


def uncover(trap: TableTrap) -> None:
    """찾아냈다. 찾은 시각을 적는다. 이제 테이블 모두가 안다."""
    trap.found_at = datetime.now(UTC)


def spring(trap: TableTrap) -> None:
    """덫이 터졌다. 끝난 시각과 까닭을 적는다."""
    end(trap, TrapEnd.SPRUNG)


def disarm(trap: TableTrap) -> None:
    """덫을 해제해 거뒀다(#806 ①-b). 끝난 시각과 까닭을 적는다."""
    end(trap, TrapEnd.DISARMED)


def end(trap: TableTrap, reason: TrapEnd) -> None:
    """덫이 끝났다. 끝난 시각과 까닭을 적는다."""
    trap.ended_at = datetime.now(UTC)
    trap.ended_reason = reason
