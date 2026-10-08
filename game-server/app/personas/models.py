# game-server/app/personas/models.py

"""
보관함의 모델. 보관함은 사람마다 캐릭터를 미리 만들어 두는 곳이다.

테이블 하나가 있다.
  - personas: 보관한 캐릭터 하나. 이름과 설명(글), 그리고 참고로 적어 둔 능력치의 점수(숫자).

보관함의 캐릭터는 그 사람만 본다. 자산(app/assets)과 달리 판도, 공개도, 등급도 없다.
판은 남이 쓰는 것을 고정하려고 있는 것인데, 보관함은 주인만 쓰고 가져갈 때 사본을 뜬다.

테이블로 가져갈 때는 사본을 뜬다. 테이블에서 바뀐 것은 보관함으로 돌아오지 않고, 보관함을 고쳐도 테이블은 그대로다.
능력치는 참고값이다. 규칙은 시나리오마다 다르다. 가져갈 때 그 테이블의 규칙과 방식으로 다시 검사한다.

스키마 이름을 적지 않는다. 연결의 search_path 가 정한다(app/core/database.py).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.assets.models import CHARACTER_DESCRIPTION_MAX_LENGTH, CHARACTER_NAME_MAX_LENGTH, TITLE_MAX_LENGTH, at_most
from app.core.database import Base

# 한 사람이 보관할 수 있는 캐릭터의 수. 끝없이 쌓아 DB 를 채우는 일을 막는다
PERSONA_MAX_PER_OWNER = 50


class Persona(Base):
    """
    보관한 캐릭터 하나.

    지우면 행을 지운다. 자산처럼 지웠다는 표시만 남기지 않는다.
    자산은 다른 자산과 테이블이 가리키지만, 보관함의 캐릭터는 아무도 가리키지 않는다. 가져간 테이블은 사본을 갖고 있다.
    """

    __tablename__ = 'personas'
    __table_args__ = (
        CheckConstraint(at_most('description', CHARACTER_DESCRIPTION_MAX_LENGTH), name='description_length'),
        # 능력치는 이름표에서 점수로 가는 묶음이다. JSON 의 null 이나 숫자 하나가 "있는 능력치"로 적히지 못한다
        CheckConstraint("abilities IS NULL OR jsonb_typeof(abilities) = 'object'", name='abilities_is_object'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 주인. 인증 서버의 public_id 다. "내 보관함"을 찾을 일이 있어 색인을 건다
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)

    name: Mapped[str] = mapped_column(String(CHARACTER_NAME_MAX_LENGTH))
    description: Mapped[str] = mapped_column(Text, default='')

    # 능력치의 점수. 참고값이다. 없을 수도 있다(글만 보관한 캐릭터).
    # none_as_null: 파이썬의 None 을 DB 의 NULL 로 적는다. 이 설정이 없으면 JSON 의 null 이라는 "값"이 적힌다
    abilities: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))

    # 능력치를 어느 룰북의 규칙으로 만들었는가. 테이블에서 저장했을 때 그 테이블의 룰북 제목을 적는다.
    # 보여 주기만 한다. 어디서 만든 숫자인지 알아보는 데 쓴다. 가져갈 때의 검사는 이 값과 상관없다
    rulebook_title: Mapped[str | None] = mapped_column(String(TITLE_MAX_LENGTH))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
