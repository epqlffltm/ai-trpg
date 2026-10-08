# game-server/app/tables/replacements.py

"""
캐릭터가 죽은 플레이어가 새 캐릭터를 들인다.

진행 중인 테이블에서는 캐릭터를 바꾸지 못한다. 길은 하나다. 자기 캐릭터가 죽었을 때 새 캐릭터를 들이는 것이다.
죽은 캐릭터는 이야기에서 퇴장하고, 새 캐릭터는 새 시트로 시작한다. 능력치와 HP 를 물려받지 않는다.

새 캐릭터를 정하는 조건은 모집 중에 캐릭터를 정할 때와 같다(app/tables/service.py 의 accept_character).
이 테이블이 허용한 방식이어야 하고, 능력치는 그 방식의 제한을 지켜야 한다. 방장의 승인은 받지 않는다.
방식과 숫자의 틀은 시나리오의 제작자와 방장이 이미 정해 뒀다. 그 안에서 만든 캐릭터는 바로 들어온다.
다른 것은 둘이다.
  - 시트를 바로 받는다. 모집 중에는 시작할 때까지 기다리지만, 진행 중에는 기다릴 "시작"이 없다.
  - 이 테이블에서 시트를 받은 적이 있는 프리젠은 고르지 못한다. 죽은 인물이 다시 걸어 들어오지 못한다.

열려 있는 라운드에만 들인다. 닫는 중인 라운드는 서술자가 읽고 있다. 그사이에 자리의 캐릭터가 바뀌면 서술이 어긋난다.
들인 것은 그 라운드에 적는다(Round.arrivals). 새 캐릭터는 그 라운드에 선언을 내지 않고, 라운드도 기다리지 않는다.
그 라운드의 장면에 아직 없는 인물이다. 라운드가 닫힐 때 서술자가 새 캐릭터를 이야기에 들이고, 다음 라운드부터 행동한다.

HTTP 를 모른다. 테이블을 잠그고 하고, 무슨 일이 있었는지를 이벤트로 적는다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import read_snapshot
from app.events import recorder
from app.events.models import EventType
from app.rounds import service as rounds
from app.rounds.models import Round
from app.tables import sheets
from app.tables.models import GameTable, TableMember
from app.tables.schemas import CharacterUpdate
from app.tables.service import (
    Conflict,
    TableConflictError,
    accept_character,
    describe_sheet,
    save,
    write_character,
)


def require_dead(member: TableMember) -> None:
    """이 사람의 캐릭터가 죽었는지 확인한다. 살아 있으면 TableConflictError. 쓰러져 있는 것은 살아 있는 것이다."""
    if not sheets.is_dead(member):
        raise TableConflictError(Conflict.CHARACTER_ALIVE)


def drop_declaration(round_: Round, user_id: uuid.UUID) -> None:
    """
    떠난 캐릭터가 이 라운드에 낸 선언이 있으면 지운다.

    쓰러진 캐릭터는 글을 낼 수 있다. 글을 내고, 캐릭터를 보내고, 같은 라운드에 새 캐릭터를 들이면 그 글이 남아 있다.
    남겨 두면 라운드가 닫힐 때 그 글이 새 캐릭터가 한 일로 읽힌다.
    """
    declaration = rounds.find_declaration(round_, user_id)
    if declaration is not None:
        round_.declarations.remove(declaration)


def note_arrival(round_: Round, member: TableMember, replaces: str) -> None:
    """
    새 캐릭터가 이 라운드에 들어왔다고 라운드에 적는다. replaces 는 그 사람의 죽은 캐릭터의 이름이다.

    목록을 고치지 않고 새 목록으로 바꿔 넣는다. 문서 칸은 안을 고친 것을 알아채지 못해서, 고치기만 하면 저장되지 않는다.
    """
    arrival = {'user_id': str(member.user_id), 'character_name': member.character_name, 'replaces': replaces}
    round_.arrivals = [*round_.arrivals, arrival]


def describe_arrival(round_: Round, member: TableMember, replaces: str) -> dict:
    """
    새 캐릭터가 들어온 것을 이벤트에 적을 모양으로 바꾼다. 시트를 준 뒤에 부른다.

    받은 시트를 함께 적는다. 시작할 때의 시트를 적는 것과 같다. 처음의 값이 기록에 있어야 뒤의 변화를 따라갈 수 있다.
    """
    return {
        'round': round_.number,
        'user_id': str(member.user_id),
        'character_name': member.character_name,
        'replaces': replaces,
        'mode': member.character_mode,
        'pregen_index': member.pregen_index,
        'number': member.sheet.number,
        'sheet': describe_sheet(member),
    }


async def bring_in_character(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, data: CharacterUpdate
) -> GameTable:
    """
    죽은 자기 캐릭터의 뒤를 이을 새 캐릭터를 들인다. 새 캐릭터는 시트를 바로 받는다.

    앉지 않았으면 TableNotFoundError.
    진행 중이 아니거나 라운드가 닫는 중이면 RoundConflictError.
    캐릭터가 살아 있거나, 이 테이블에서 허용하지 않는 방식이거나, 고를 수 없는 프리젠이거나,
    주사위 방식인데 새 캐릭터를 위해 아직 굴리지 않았으면 TableConflictError.
    없는 프리젠이거나, 정한 능력치가 이 테이블의 규칙에 맞지 않으면 TableOptionError.

    테이블을 잠그고 한다. 같은 사람의 요청 둘이 동시에 와도 새 캐릭터는 하나만 들어온다.
    확인을 모두 끝낸 뒤에 고친다. 받을 시트가 없는 캐릭터를 자리에 적지 않는다.
    """
    table, member, round_ = await rounds.lock_current_round(session, user_id, table_id)
    require_dead(member)
    rounds.require_open(round_)
    snapshot = read_snapshot(table.content)
    chosen = accept_character(table, snapshot, member, data)
    # 그 방식을 허용한 판에는 받을 시트가 반드시 있다(게시 조건). 없으면 들일 수 없는 캐릭터다
    source = sheets.source_of(snapshot, chosen.pregen_index, chosen.abilities)
    if source is None:
        raise TableConflictError(Conflict.CHARACTERS_MISSING)

    replaces = member.character_name
    write_character(member, chosen)
    sheets.give_sheet(member, source)
    drop_declaration(round_, user_id)
    note_arrival(round_, member, replaces)
    payload = describe_arrival(round_, member, replaces)
    recorder.record(session, table, EventType.CHARACTER_JOINED, actor_id=user_id, payload=payload)
    return await save(session, table)
