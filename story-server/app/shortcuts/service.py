# story-server/app/shortcuts/service.py

"""
내 단축어를 asset 서버에서 가져오고(#981), 세션에서 고를 수 있는 단축어를 모은다.
내 단축어는 판이 없어 말을 보낼 때마다 읽는다.

  - 말이 "/이름"으로 시작할 때만 부른다. 아니면 부르지 않는다(보통의 말에 바깥 호출을 더하지 않는다)
  - 이름이 세계관의 판에 있어도 부른다. 판은 차례를 잡은 뒤에 읽고, 바깥을 부르는 동안 DB 의 연결을 쥐지 않으려고
    차례를 잡기 전에 부른다
  - asset 서버를 쓸 수 없으면 내 단축어가 없는 것으로 본다. 말은 그대로 보낸다(작품의 단축어는 쓴다)
  - 목록(available)도 asset 서버를 먼저 부르고 DB 를 읽는다
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.client import AssetClient, AssetNotFoundError, AssetUnavailableError
from app.assets.schemas import ShortcutDocument, shortcuts_of
from app.conversations.service import get_conversation
from app.core.dependencies import Viewer
from app.shortcuts.calls import choosable, split_call
from app.shortcuts.schemas import ShortcutOut, ShortcutSource

logger = logging.getLogger(__name__)


async def fetch_mine(asset: AssetClient, viewer: Viewer) -> tuple[ShortcutDocument, ...]:
    """그 사람의 단축어들. 가져오지 못하면 빈 것이다."""
    try:
        found = await asset.fetch_shortcuts(viewer.token)
    except (AssetUnavailableError, AssetNotFoundError) as error:
        logger.warning('내 단축어를 가져오지 못했다(%s). 작품의 단축어만 쓴다', type(error).__name__)
        return ()
    return tuple(found.items)


async def mine_for(asset: AssetClient, viewer: Viewer, content: str) -> tuple[ShortcutDocument, ...]:
    """그 말에 쓸 내 단축어들. 단축어를 부르지 않은 말이거나 가져오지 못하면 빈 것이다."""
    if split_call(content) is None:
        return ()
    return await fetch_mine(asset, viewer)


def listed(shortcut: ShortcutDocument, from_work: bool) -> ShortcutOut:
    """목록에 싣는 단축어 하나. 본문은 싣지 않는다."""
    source = ShortcutSource.WORK if from_work else ShortcutSource.MINE
    return ShortcutOut(name=shortcut.name, description=shortcut.description, source=source)


async def available(
    session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID, mine: tuple[ShortcutDocument, ...]
) -> list[ShortcutOut]:
    """그 세션에서 고를 수 있는 단축어들(mine 은 미리 가져온 내 단축어). 남의 세션이면 ConversationNotFoundError."""
    _, imported = await get_conversation(session, viewer, conversation_id)
    work = shortcuts_of(imported.document)
    return [listed(shortcut, from_work) for shortcut, from_work in choosable(work, mine)]
