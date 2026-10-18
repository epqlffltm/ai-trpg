# game-server/app/tables/building.py

"""
테이블을 만드는 데 쓰는 것들. 초대 코드, 정원의 상한, 문체, 판에서 테이블 객체 만들기, 비밀번호.

DB 를 모른다. 판에서 테이블 객체를 만들 뿐 저장하지 않는다(build_table).
비밀번호의 계산은 느려서 다른 스레드에서 돌린다(hash_table_password, check_table_password).
"""

import asyncio
import secrets
import uuid

from app.assets.models import TABLE_MAX_PLAYERS, CharacterMode, NarrationStyle, ScenarioVersion
from app.assets.scenarios.snapshot import Snapshot
from app.auth.tokens import AccessClaims
from app.listings import service as listings
from app.tables import passwords
from app.tables.errors import (
    WrongPasswordError,
)
from app.tables.models import GameTable, TableMember
from app.tables.schemas import TableCreate


def new_invite_code() -> str:
    """추측할 수 없는 초대 코드를 만든다. 9 바이트를 글자로 바꾸면 12 글자다."""
    return secrets.token_urlsafe(9)


def seat_limit(viewer: AccessClaims, snapshot: Snapshot) -> int:
    """
    이 사람이 이 판으로 테이블을 만들 때 둘 수 있는 가장 큰 정원.

    볼 수 없는 등급의 판이면(지금은 성인용 전부) 혼자서만 한다. 제작자가 자기 것을 시험해 보는 용도다.
    성인 인증이 생기면 allowed_ratings 가 성인용을 돌려주고, 이 제한은 저절로 풀린다.
    """
    if snapshot.rating in listings.allowed_ratings(viewer):
        return TABLE_MAX_PLAYERS
    return 1


def choose_narration_style(snapshot: Snapshot, chosen: NarrationStyle | None) -> NarrationStyle:
    """방장이 고른 문체. 고르지 않았으면(None) 판의 추천 문체다."""
    return chosen or snapshot.narration_style


def build_table(
    host_id: uuid.UUID,
    version: ScenarioVersion,
    snapshot: Snapshot,
    data: TableCreate,
    modes: list[CharacterMode],
    password_hash: str | None,
) -> GameTable:
    """
    판에서 테이블 객체를 만든다. 아직 저장하지 않는다.

    판의 내용을 통째로 복사해 온다. 옛 형식의 판이면 지금의 모양으로 올린 것을 복사한다.
    만든 사람이 방장이자 첫 참가자다. modes 는 이 테이블에서 허용할 캐릭터 방식이다.
    password_hash 는 비밀번호를 계산해 둔 값이다. 비밀번호가 없으면 None 이다.
    """
    return GameTable(
        host_id=host_id,
        version_id=version.id,
        title=snapshot.title,
        # mode='json': UUID 같은 값을 JSON 에 넣을 수 있는 글자로 바꾼다
        content=snapshot.model_dump(mode='json'),
        opening_index=data.opening_index,
        capacity=data.capacity,
        character_modes=modes,
        rating=snapshot.rating,
        invite_code=new_invite_code(),
        is_public=data.is_public,
        password_hash=password_hash,
        narration_style=choose_narration_style(snapshot, data.narration_style),
        round_time_limit=data.round_time_limit,
        narration_tier=data.narration_tier,
        narration_model=data.narration_model,
        credit_wait_seconds=data.credit_wait_seconds,
        remove_short_payers=data.remove_short_payers,
        whisper_notice=data.whisper_notice,
        ledger_drafts=data.ledger_drafts,
        members=[TableMember(user_id=host_id)],
    )


async def hash_table_password(password: str | None) -> str | None:
    """
    비밀번호를 저장할 모양으로 바꾼다. 비밀번호가 없으면 None.

    to_thread: 계산을 다른 스레드에서 돌린다. 0.2 초 동안 서버가 다른 요청을 받지 못하는 일을 막는다.
    """
    if password is None:
        return None
    return await asyncio.to_thread(passwords.hash_password, password)


async def check_table_password(table: GameTable, password: str | None) -> None:
    """
    테이블의 비밀번호가 맞는지 확인한다. 틀렸으면 WrongPasswordError.

    비밀번호가 없는 테이블이면 무엇을 보내든 통과한다.
    """
    if table.password_hash is None:
        return
    if password is None or not await asyncio.to_thread(passwords.verify_password, password, table.password_hash):
        raise WrongPasswordError
