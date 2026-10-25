# board-server/app/withdrawal/service.py

"""
탈퇴한 사람의 것을 정리한다(docs/architecture/withdrawal.md 의 게시판 줄). HTTP 를 모른다.

  - 글과 댓글은 남긴다. 함께한 사람의 대화다. 글쓴이(author_id)만 비운다. 화면은 "탈퇴한 사용자"로 그린다
  - 신고는 남긴다. 운영의 기록이다. 신고한 사람(reporter_id)만 비운다. 처리한 운영자(handled_by)는 남긴다
  - 적어 둔 닉네임(authors)은 지운다
  - 그 사람에게 보낼 알림(발송함)은 지운다. 받을 사람이 없다

번호를 남기지 않는 까닭: 응답의 author_id 는 누구나 본다. 남기면 탈퇴한 사람의 글을 한데 모을 수 있다.
비운 뒤에는 그 글과 댓글을 고칠 사람이 없다. 운영자만 지운다.

한 트랜잭션이다. 몇 번을 불러도 같다. 두 번째에는 바꿀 줄이 없다. 이 서버가 모르는 사람도 바꿀 줄이 없을 뿐이다.
다른 모듈의 서비스를 부르지 않고 테이블에 직접 닿는다(repository.py). 그래야 한 트랜잭션으로 묶기 쉽다.
"""

import logging
import uuid
from dataclasses import asdict, dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications import outbox
from app.withdrawal import repository

logger = logging.getLogger(__name__)

# 로그의 operation(docs/observability.md)
WITHDRAWAL_OPERATION = 'board.withdrawal'


@dataclass(frozen=True)
class Erased:
    """그 사람의 것을 정리한 수. 이미 정리했거나 모르는 사람이면 모두 0 이다."""

    # 글쓴이를 비운 글(지운 글 포함)
    blanked_posts: int
    # 글쓴이를 비운 댓글(지운 댓글 포함)
    blanked_comments: int
    # 신고한 사람을 비운 신고
    blanked_reports: int
    # 지운 닉네임(0 이나 1)
    deleted_authors: int
    # 지운, 아직 보내지 않은 알림
    deleted_notifications: int


async def erase(session: AsyncSession, user_id: uuid.UUID) -> Erased:
    """그 사람의 것을 정리하고 저장한다. 한 트랜잭션이다. 중간에 실패하면 아무것도 바뀌지 않는다."""
    erased = Erased(
        blanked_posts=await repository.blank_post_authors(session, user_id),
        blanked_comments=await repository.blank_comment_authors(session, user_id),
        blanked_reports=await repository.blank_reporter(session, user_id),
        deleted_authors=await repository.delete_author(session, user_id),
        deleted_notifications=await outbox.drop_for_user(session, user_id),
    )
    await session.commit()
    return erased


def log_erased(erased: Erased) -> None:
    """정리한 수를 남긴다. 사람(user_id)은 남기지 않는다."""
    logger.info('탈퇴한 사람의 것을 정리했다', extra={'operation': WITHDRAWAL_OPERATION, **asdict(erased)})
