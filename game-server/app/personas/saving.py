# game-server/app/personas/saving.py

"""
테이블의 내 캐릭터를 보관함에 저장한다.

테이블에서 즉석으로 만든 캐릭터를 다른 테이블에서도 쓰려는 것이다. 저장하는 것은 사본이다.
저장한 뒤에 테이블에서 바뀐 것은 보관함으로 오지 않는다.

저장하는 것은 캐릭터의 처음 모습이다. 이름, 설명, 시작할 때의 능력치.
HP 와 죽음의 굴림에서 센 것은 저장하지 않는다. 그 이야기 안의 상태라, 다른 테이블로 들고 갈 숫자가 아니다.
최대 HP 도 저장하지 않는다. 플레이어가 정한 능력치의 최대 HP 는 가져간 테이블의 규칙으로 다시 구한다.
죽은 캐릭터도 저장할 수 있다. 다른 이야기에서는 살아 있는 인물이다.

프리젠은 저장하지 못한다. 시나리오의 제작자가 쓴 인물이다.
보관함은 등급이 없어서, 성인용 시나리오의 프리젠이 저장되면 전체 이용가 테이블로 걸어 들어갈 길이 생긴다.

테이블은 읽기만 한다. 잠그지 않는다. 바꾸는 것은 보관함이고, 보관함은 보관함대로 잠근다(app/personas/service.py).
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import CharacterMode
from app.assets.scenarios.snapshot import Snapshot, read_snapshot
from app.personas import service
from app.personas.models import Persona
from app.personas.service import Conflict, PersonaConflictError
from app.tables import service as tables
from app.tables import sheets
from app.tables.models import TableMember


def require_keepable(member: TableMember) -> None:
    """
    이 자리의 캐릭터를 보관함에 저장할 수 있는지 확인한다. 아니면 PersonaConflictError.

    캐릭터를 아직 정하지 않았으면 저장할 것이 없다. 프리젠은 저장하지 못한다.
    """
    if member.character_name is None:
        raise PersonaConflictError(Conflict.NO_CHARACTER)
    if member.character_mode == CharacterMode.PREGEN:
        raise PersonaConflictError(Conflict.PREGEN_NOT_KEPT)


def starting_abilities(snapshot: Snapshot, member: TableMember) -> dict[str, int] | None:
    """
    이 캐릭터의 시작할 때의 능력치. 받을 숫자가 없으면 None.

    시트를 줄 때와 같은 길로 찾는다(app/tables/sheets.py 의 find_source). 시작하기 전이어도, 진행 중이어도 같은 값이다.
    능력치는 플레이하면서 바뀌지 않는다. 바뀌는 것(HP, 죽음의 굴림)은 시트에만 있고, 여기서 읽지 않는다.
    """
    source = sheets.find_source(snapshot, member)
    return dict(source.abilities) if source is not None else None


def from_member(owner_id: uuid.UUID, member: TableMember, abilities: dict[str, int] | None, title: str) -> Persona:
    """자리의 캐릭터에서 보관함의 캐릭터를 만든다. 아직 저장하지 않는다. title 은 그 테이블의 룰북의 제목이다."""
    return Persona(
        owner_id=owner_id,
        name=member.character_name,
        description=member.character_description,
        abilities=abilities,
        rulebook_title=title,
    )


async def save_character(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID) -> Persona:
    """
    테이블의 내 캐릭터를 보관함에 저장한다. 저장한 캐릭터를 돌려준다.

    앉지 않았으면 TableNotFoundError.
    캐릭터가 없거나, 프리젠이거나, 보관함이 가득 찼으면 PersonaConflictError.
    같은 캐릭터를 여러 번 저장하면 여러 개가 생긴다. 보관함의 캐릭터는 저장한 때의 사본이다.
    """
    table = await tables.get_table(session, user_id, table_id)
    member = tables.require_member(table, user_id)
    require_keepable(member)
    snapshot = read_snapshot(table.content)
    persona = from_member(user_id, member, starting_abilities(snapshot, member), snapshot.rulebook.title)
    return await service.keep(session, persona)
