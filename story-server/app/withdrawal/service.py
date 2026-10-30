# story-server/app/withdrawal/service.py

"""
탈퇴한 사람의 것을 지운다(docs/architecture/withdrawal.md 의 "마칠 때: 다른 서버", chat 과 같다).

  - 세션과 딸린 것(말, 상태, 요약, 기억 메모, 페르소나의 사본)을 지운다
  - 가져온 세계관의 판의 사본과 그 로어북의 벡터를 지운다. asset 서버의 원본(공개 세계관)은 그 서버의 일이다
  - 계정의 기록(본 엔딩, 연 일러스트)을 지운다
  - 청구 기록(generations)은 남긴다. 세션과 말을 가리키는 칸만 비운다(chat 과 같다, 2026-10-23 유저 결정).
    남는 것은 공개 ID, 모델, 토큰 수, 원가, 청구 상태, 홀드의 이름표다. 글은 남지 않는다
한 트랜잭션이다. 같은 알림이 다시 와도 결과가 같다. 지울 것이 없으면 아무것도 지우지 않는다(멱등).
유예 동안(7일)은 토큰이 이 서버에 통하지 않으므로 지우는 사이에 새 말이 생기지 않는다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.withdrawal import repository


async def erase_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """그 사람의 세션과 판의 사본, 계정의 기록을 지우고 저장한다."""
    await repository.delete_conversations_owned(session, user_id)
    await repository.delete_worlds_owned(session, user_id)
    await repository.delete_records_owned(session, user_id)
    await session.commit()
