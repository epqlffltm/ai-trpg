# asset-server/app/personas/models.py

"""
계정 페르소나의 테이블 모델(#565). 한 사람이 여러 개를 갖고, 하나를 기본으로 둔다.

계정 페르소나는 TRPG, chat, story 가 함께 쓰는 "나"의 설정이다(docs/architecture/asset-server.md 의 "계정 페르소나").
  - 판이 없다. 주인만 보고 고친다. 쓰는 서비스는 세션을 시작할 때 사본을 뜬다.
  - 고칠 때마다 revision 이 오른다. 세션은 가져간 revision 을 적어 두고, 지금 것과 다르면 "새 설정으로 바꾸기"를 보인다.
  - 지우면 행을 지운다. 가져간 세션은 사본으로 돈다.
  - 나이와 성별은 적어 두는 글이다. 서버는 이것으로 거르거나 막지 않는다(2026-10-21).
이름과 설명의 길이는 TRPG 의 보관함(trpg-server 의 app/personas)과 같다. 나중에 보관함을 나눌 때 그대로 옮긴다.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 이름. TRPG 의 캐릭터 이름과 같다
PERSONA_NAME_MAX_LENGTH = 50
# 설명. TRPG 의 캐릭터 설명과 같다
PERSONA_DESCRIPTION_MAX_LENGTH = 1000
# 나이와 성별. 고르는 칸이 아니라 적는 글이다("스물셋", "천 살쯤", "알 수 없음")
PERSONA_AGE_MAX_LENGTH = 20
PERSONA_GENDER_MAX_LENGTH = 20
# 호칭. 모델이 나를 부르는 말("선배", "주인님")
PERSONA_ADDRESS_MAX_LENGTH = 30
# 말투 예시와 성격. 모델이 읽는다. 대화마다 프롬프트에 들어가므로 길이가 곧 값이다
PERSONA_SPEECH_MAX_LENGTH = 1000
PERSONA_PERSONALITY_MAX_LENGTH = 1000


def at_most(column: str, max_length: int) -> str:
    """컬럼의 글자 수가 제한을 넘지 않아야 한다는 조건을 SQL 로 만든다."""
    return f'char_length({column}) <= {max_length}'


class Persona(Base):
    """계정 페르소나 하나."""

    __tablename__ = 'personas'
    __table_args__ = (
        CheckConstraint(at_most('description', PERSONA_DESCRIPTION_MAX_LENGTH), name='description_length'),
        CheckConstraint(at_most('speech_examples', PERSONA_SPEECH_MAX_LENGTH), name='speech_examples_length'),
        CheckConstraint(at_most('personality', PERSONA_PERSONALITY_MAX_LENGTH), name='personality_length'),
        CheckConstraint('revision >= 1', name='revision_positive'),
        # 한 사람의 기본은 하나뿐이다. 기본을 바꾸는 두 요청이 겹쳐도 둘이 되지 않게 DB 가 막는다
        Index('uq_personas_default_per_owner', 'owner_id', unique=True, postgresql_where=text('is_default')),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 주인. 인증 서버의 public_id 다. "이 사람의 페르소나들"을 찾는 일이 대부분이라 색인을 건다
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)

    # 이름. 길이는 칸의 크기(varchar)가 막는다
    name: Mapped[str] = mapped_column(String(PERSONA_NAME_MAX_LENGTH))
    description: Mapped[str] = mapped_column(Text, default='', server_default='')

    # 프로필 그림의 id. 자기가 올린 그림만 붙인다(app/personas/service.py). 그림이 지워지면 비운다
    image_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey('images.id', ondelete='SET NULL'), default=None, index=True
    )

    age: Mapped[str] = mapped_column(String(PERSONA_AGE_MAX_LENGTH), default='', server_default='')
    gender: Mapped[str] = mapped_column(String(PERSONA_GENDER_MAX_LENGTH), default='', server_default='')
    form_of_address: Mapped[str] = mapped_column(String(PERSONA_ADDRESS_MAX_LENGTH), default='', server_default='')
    speech_examples: Mapped[str] = mapped_column(Text, default='', server_default='')
    personality: Mapped[str] = mapped_column(Text, default='', server_default='')

    # 기본인가. 한 사람에 하나다(위의 색인). 페르소나가 있으면 늘 하나가 기본이다(app/personas/service.py)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('false'))

    # 고친 횟수 + 1. 내용(이름부터 성격까지)이 바뀔 때만 오른다. 기본으로 두는 것은 내용이 아니다
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default='1')

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
