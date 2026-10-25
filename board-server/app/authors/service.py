# board-server/app/authors/service.py

"""
글쓴이의 닉네임을 기억하고 찾는다.

로그인한 요청마다 토큰의 닉네임을 적는다(app/core/auth.py 의 Member). 같은 닉네임이면 쓰지 않는다.
  - 최근에 적은 닉네임을 프로세스 안에 기억해 둔다(RecentNicknames). 같은 사람의 요청마다 DB 에 쓰지 않는다
  - DB 에도 "다를 때만 고친다" 를 건다. 기억이 없는 다른 프로세스가 와도 같은 줄을 다시 고치지 않는다
  - 토큰의 닉네임이 받을 수 없는 모양(빈 글, 보이지 않는 글자, 너무 긴 것)이면 적지 않는다. 토큰은 받는다
"""

import re
import unicodedata
import uuid
from collections.abc import Iterable

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.authors.models import NICKNAME_MAX_LENGTH, Author

# 기억해 두는 사람의 수. 넘치면 모두 잊고 다시 시작한다(줄마다 시각을 세는 것보다 단순하다)
RECENT_NICKNAMES_MAX = 10_000

# 보이지 않는 글자(제어, 서식, 할당되지 않은 글자, 사적 사용). 유니코드의 일반 범주 C
INVISIBLE_CATEGORIES = ('Cc', 'Cf', 'Cn', 'Co', 'Cs')
VISIBLE = re.compile(r'\S')

UPSERT_NICKNAME = text(
    """
    INSERT INTO authors (user_id, nickname) VALUES (:user_id, :nickname)
    ON CONFLICT (user_id) DO UPDATE
       SET nickname = EXCLUDED.nickname, updated_at = now()
     WHERE authors.nickname IS DISTINCT FROM EXCLUDED.nickname
    """
)


def has_invisible(value: str) -> bool:
    """보이지 않는 글자가 있는가."""
    return any(unicodedata.category(character) in INVISIBLE_CATEGORIES for character in value)


def read_nickname(value: object) -> str | None:
    """토큰의 닉네임을 받을 수 있으면 그대로, 아니면 None 이다."""
    if not isinstance(value, str):
        return None
    if not VISIBLE.search(value) or has_invisible(value):
        return None
    if len(value) > NICKNAME_MAX_LENGTH:
        return None
    return value


class RecentNicknames:
    """최근에 적은 닉네임. 사람마다 마지막 것 하나다."""

    def __init__(self, max_size: int = RECENT_NICKNAMES_MAX) -> None:
        self._max_size = max_size
        self._remembered: dict[uuid.UUID, str] = {}

    def has(self, user_id: uuid.UUID, nickname: str) -> bool:
        return self._remembered.get(user_id) == nickname

    def remember(self, user_id: uuid.UUID, nickname: str) -> None:
        if user_id not in self._remembered and len(self._remembered) >= self._max_size:
            self._remembered.clear()
        self._remembered[user_id] = nickname

    def clear(self) -> None:
        self._remembered.clear()


async def remember(session: AsyncSession, recent: RecentNicknames, user_id: uuid.UUID, nickname: str) -> None:
    """그 사람의 닉네임을 적는다. 최근에 같은 것을 적었으면 하지 않는다. 바로 저장한다."""
    if recent.has(user_id, nickname):
        return
    await session.execute(UPSERT_NICKNAME, {'user_id': user_id, 'nickname': nickname})
    await session.commit()
    recent.remember(user_id, nickname)


async def nicknames_of(session: AsyncSession, user_ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    """사람들의 닉네임. 모르는 사람과 비운 글쓴이(None)는 빠진다."""
    known = {user_id for user_id in user_ids if user_id is not None}
    if not known:
        return {}
    rows = await session.execute(select(Author.user_id, Author.nickname).where(Author.user_id.in_(known)))
    return {user_id: nickname for user_id, nickname in rows.all()}
