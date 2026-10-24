# story-server/app/conversations/service.py

"""
세션을 시작하고, 목록으로 내주고, 하나를 읽는다(docs/architecture/story.md 의 만드는 순서 1).

세션을 시작하는 길.
  1. asset 서버에서 세계관의 마지막 판을 가져온다. DB 의 트랜잭션을 열기 전에, 연결을 쥐지 않은 채로 부른다
  2. 가져온 판의 등급을 이 서버의 규칙으로 한 번 더 본다(allowed_ratings)
  3. 판의 사본(사람마다, 판마다 하나)과 세션을 한 트랜잭션에서 저장한다
쓸 수 있는 세계관인지는 asset 서버가 판단한다(주인이거나, 공개이고 판의 등급을 볼 수 있는 사람).

지키는 것.
  - 남의 세션은 없는 것과 같다(ConversationNotFoundError, 404). 볼 수 없는 등급의 세션도 그렇다.
  - 사본은 가져온 뒤 바뀌지 않는다. 원본이 다시 게시돼도 그 세션은 처음의 판으로 돈다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.client import AssetAdultRequiredError, AssetClient, AssetNotFoundError
from app.assets.schemas import WorldCopy
from app.conversations import repository
from app.conversations.models import Conversation, ImportedWorld
from app.conversations.repository import ConversationRow
from app.core.dependencies import Viewer
from app.ratings import allowed_ratings


class ConversationNotFoundError(Exception):
    """그런 세션이 없다. 남의 것, 볼 수 없는 등급의 것도 이것이다."""


class WorldNotFoundError(Exception):
    """asset 서버가 그 세계관을 쓸 수 없다고 했다(없다, 남의 비공개다, 게시한 적이 없다, 볼 수 없는 등급이다)."""


class AdultContentRequiredError(Exception):
    """자기 세계관인데 등급을 쓸 수 없다. 화면이 본인인증으로 안내한다(403)."""


# --- 고르기와 만들기. DB 와 바깥을 모른다 ---


def require_usable_rating(copy: WorldCopy, viewer: Viewer) -> None:
    """가져온 판의 등급을 이 사람이 쓸 수 있는가. asset 서버가 이미 봤지만 이 서버의 규칙으로 한 번 더 본다."""
    if copy.rating not in allowed_ratings(viewer.claims):
        raise WorldNotFoundError


def build_world(owner_id: uuid.UUID, copy: WorldCopy) -> ImportedWorld:
    """판의 사본을 만든다. 문서는 받은 칸 전부다. 아직 저장하지 않는다."""
    return ImportedWorld(
        id=uuid.uuid4(),
        owner_id=owner_id,
        source_id=copy.id,
        version=copy.version,
        name=copy.document.name,
        rating=copy.rating,
        document=copy.document.model_dump(mode='json'),
    )


def build_conversation(owner_id: uuid.UUID, world: ImportedWorld) -> Conversation:
    """세션을 만든다. 제목은 세계관의 이름이다. 아직 저장하지 않는다."""
    return Conversation(id=uuid.uuid4(), owner_id=owner_id, world_id=world.id, title=world.name)


# --- asset 서버를 부르기 ---


async def fetch_world(asset: AssetClient, viewer: Viewer, world_id: uuid.UUID) -> WorldCopy:
    """세계관의 마지막 판. asset 서버의 404 와 403 을 이 서버의 예외로 바꾼다. 닿지 못하면 AssetUnavailableError."""
    try:
        return await asset.fetch_world(viewer.token, world_id)
    except AssetNotFoundError as error:
        raise WorldNotFoundError from error
    except AssetAdultRequiredError as error:
        raise AdultContentRequiredError from error


# --- 저장과 읽기 ---


async def save_conversation(session: AsyncSession, owner_id: uuid.UUID, copy: WorldCopy) -> uuid.UUID:
    """판의 사본과 세션을 한 번에 저장하고 세션의 id 를 돌려준다."""
    world = await repository.keep_world(session, build_world(owner_id, copy))
    conversation = build_conversation(owner_id, world)
    repository.add(session, conversation)
    await session.commit()
    return conversation.id


async def start_conversation(
    session: AsyncSession, asset: AssetClient, viewer: Viewer, world_id: uuid.UUID
) -> uuid.UUID:
    """
    세션을 시작하고 그 id 를 돌려준다. 실패하면 WorldNotFoundError, AdultContentRequiredError, AssetUnavailableError.

    asset 서버는 DB 의 트랜잭션을 열기 전에 부른다(기다리는 동안 연결을 쥐지 않는다).
    """
    copy = await fetch_world(asset, viewer, world_id)
    require_usable_rating(copy, viewer)
    return await save_conversation(session, viewer.claims.user_id, copy)


async def get_conversation(session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID) -> ConversationRow:
    """이 사람의 세션 하나와 판의 사본. 없으면 ConversationNotFoundError."""
    found = await repository.find_visible(
        session, viewer.claims.user_id, allowed_ratings(viewer.claims), conversation_id
    )
    if found is None:
        raise ConversationNotFoundError
    return found


async def list_conversations(
    session: AsyncSession, viewer: Viewer, source_id: uuid.UUID | None, limit: int, offset: int
) -> tuple[list[ConversationRow], int]:
    """이 사람의 세션의 한 쪽과 전체 개수. 볼 수 있는 등급만이다."""
    return await repository.list_visible(
        session, viewer.claims.user_id, allowed_ratings(viewer.claims), source_id, limit, offset
    )
