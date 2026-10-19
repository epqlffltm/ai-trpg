# trpg-server/app/whispers/service.py

"""
쪽지를 보내고 읽는다(#196).

HTTP 를 모른다. SQL 을 모른다. 어디까지를 한 묶음으로 저장할지(커밋)는 여기서 정한다.

  - 앉은 사람만 보내고 읽는다. 받는 사람도 앉아 있어야 한다. 자기 자신에게는 보내지 않는다.
  - 끝난 테이블에는 보내지 못한다. 읽기는 된다(채팅과 같다).
  - 보내는 일은 테이블의 행을 잠그고 한다. 쪽지함의 번호를 "가장 큰 번호 + 1"로 정하기 때문이다.
  - 채팅과 같은 수로 함께 센다. 쪽지로 채팅의 제한을 돌아가지 못한다.
  - 테이블이 알리기로 했으면(whisper_notice) "누가 누구에게 보냈다"를 이벤트로 남긴다. 글은 싣지 않는다.

입력 중 표시는 없다. 띄우면 누가 누구에게 쓰는지 드러난다.
저장하면서 "쪽지가 생겼다"는 신호를 보낸다. 누구의 쪽지인지는 싣지 않는다. 깨어난 스트림이 각자 자기 쪽지함을 읽는다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType
from app.limits.setup import Limiting
from app.realtime import signals
from app.realtime.signals import Kind, Signal
from app.rounds import repository as round_repository
from app.rounds.models import Round, RoundStatus
from app.tables import service as tables
from app.tables import state as table_state
from app.tables.errors import MemberNotFoundError, TableOptionError
from app.tables.models import GameTable, TableMember
from app.whispers import repository
from app.whispers.models import Whisper
from app.whispers.schemas import WhisperCreate


def target_round(latest: Round | None) -> int:
    """
    지금 보내는 쪽지가 들어갈 라운드의 번호.

    열린 라운드가 있으면 그 라운드다. 닫는 중이거나 닫혔으면(서술 중, 다음 라운드가 열리기 전) 다음 라운드다.
    아직 시작하지 않았으면 첫 라운드다.
    닫기 시작한 라운드에는 더 넣지 않는다. 서술을 다시 맡겨도 서술자가 같은 쪽지를 받게 한다.
    """
    if latest is None:
        return 1
    if latest.status == RoundStatus.OPEN:
        return latest.number
    return latest.number + 1


def find_recipient(table: GameTable, sender_id: uuid.UUID, recipient_id: uuid.UUID) -> TableMember:
    """
    받는 사람의 자리를 찾는다.

    자기 자신이면 TableOptionError(recipient_id). 앉아 있지 않으면 MemberNotFoundError.
    """
    if recipient_id == sender_id:
        raise TableOptionError('recipient_id')
    recipient = table_state.find_member(table, recipient_id)
    if recipient is None:
        raise MemberNotFoundError
    return recipient


async def next_sequence(session: AsyncSession, table_id: uuid.UUID, owner_id: uuid.UUID) -> int:
    """
    이 쪽지함의 다음 번호.

    테이블을 잠근 뒤에 부른다. 잠그지 않으면 두 요청이 같은 번호를 받는다(그때는 DB 의 유일 조건이 막는다).
    쪽지함은 자리와 따로 남는다. 나갔다 다시 앉아도 번호가 이어진다.
    """
    return await repository.last_sequence(session, table_id, owner_id) + 1


def build_copy(
    table: GameTable,
    owner_id: uuid.UUID,
    sequence: int,
    sender: TableMember,
    recipient: TableMember,
    data: WhisperCreate,
    round_number: int,
) -> Whisper:
    """한 사람의 쪽지함에 넣을 쪽지 한 장을 만든다. 아직 저장하지 않는다. 쓸 때의 캐릭터 이름을 함께 적는다."""
    return Whisper(
        table_id=table.id,
        owner_id=owner_id,
        sequence=sequence,
        sender_id=sender.user_id,
        recipient_id=recipient.user_id,
        sender_character_name=sender.character_name,
        recipient_character_name=recipient.character_name,
        content=data.content,
        gm_visible=data.gm_visible,
        round_number=round_number,
    )


def announce(session: AsyncSession, table: GameTable, sender: TableMember, recipient: TableMember) -> None:
    """
    테이블이 알리기로 했으면 "누가 누구에게 쪽지를 보냈다"를 이벤트로 남긴다. 글은 싣지 않는다.

    알리지 않는 테이블에는 아무것도 남기지 않는다.
    """
    if not table.whisper_notice:
        return
    payload = {
        'user_id': str(sender.user_id),
        'character_name': sender.character_name,
        'recipient_id': str(recipient.user_id),
        'recipient_character_name': recipient.character_name,
    }
    recorder.record(session, table, EventType.WHISPER_SENT, actor_id=sender.user_id, payload=payload)


async def post_whisper(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, data: WhisperCreate, limiting: Limiting
) -> Whisper:
    """
    쪽지를 보낸다. 보낸 사람의 쪽지함에 적힌 것을 돌려준다.

    앉지 않았으면 TableNotFoundError, 끝난 테이블이면 TableConflictError.
    받는 사람이 자기 자신이면 TableOptionError, 앉아 있지 않으면 MemberNotFoundError.
    채팅과 같은 수로 센다(limiting.limits.chat). 넘으면 TooManyAttempts. 잠그기 전에 센다.

    테이블을 잠그고 한다. 두 사람이 동시에 보내도 쪽지함의 번호가 겹치지 않는다.
    """
    await limiting.limiter.count_attempt(limiting.limits.chat, f'{table_id}:{user_id}')
    table, sender = await tables.lock_seated(session, user_id, table_id)
    table_state.require_not_ended(table)
    recipient = find_recipient(table, user_id, data.recipient_id)
    round_number = target_round(await round_repository.find_latest_round(session, table.id))

    copies = [
        build_copy(
            table, owner_id, await next_sequence(session, table.id, owner_id), sender, recipient, data, round_number
        )
        for owner_id in (sender.user_id, recipient.user_id)
    ]
    for copy in copies:
        repository.add_whisper(session, copy)
    announce(session, table, sender, recipient)
    # 신호는 커밋될 때 함께 나간다. 이벤트의 신호는 tables.commit 이 보낸다
    await signals.publish(session, Signal(table_id=table.id, kind=Kind.WHISPERS))
    await tables.commit(session, table)
    # DB 가 정한 값(보낸 시각)을 읽어 온다
    sent = copies[0]
    await session.refresh(sent)
    return sent


async def list_whispers(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, after: int, limit: int
) -> tuple[int, list[Whisper]]:
    """
    자기 쪽지함의 쪽지 중 after 번 뒤의 것을 순서대로 돌려준다. 쪽지함의 마지막 번호도 함께 돌려준다.

    앉지 않았으면 TableNotFoundError. 끝난 테이블의 쪽지도 읽을 수 있다.
    """
    await tables.get_table(session, user_id, table_id)
    whispers = await repository.list_after(session, table_id, user_id, after, limit)
    return await repository.last_sequence(session, table_id, user_id), whispers
