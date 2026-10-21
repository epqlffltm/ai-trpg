# asset-server/app/personas/schemas.py

"""
계정 페르소나 API 가 받는 입력과 내보내는 응답의 모양.

길이는 모델의 상수를 그대로 쓴다. DB 의 CHECK 와 숫자가 어긋나지 않는다.
DB 의 CHECK 는 마지막 방어선이고, 사용자에게 "어느 칸이 왜 틀렸는지" 알려 주는 것은 이쪽이다.
"""

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.personas.models import (
    PERSONA_ADDRESS_MAX_LENGTH,
    PERSONA_AGE_MAX_LENGTH,
    PERSONA_DESCRIPTION_MAX_LENGTH,
    PERSONA_GENDER_MAX_LENGTH,
    PERSONA_NAME_MAX_LENGTH,
    PERSONA_PERSONALITY_MAX_LENGTH,
    PERSONA_SPEECH_MAX_LENGTH,
)

# 이름은 앞뒤 공백을 떼고, 그러고도 한 글자 이상이어야 한다. 공백만 있는 이름을 막는다
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=PERSONA_NAME_MAX_LENGTH)]
Description = Annotated[str, StringConstraints(max_length=PERSONA_DESCRIPTION_MAX_LENGTH)]
# 짧은 칸은 앞뒤 공백을 뗀다. 비워도 된다
Age = Annotated[str, StringConstraints(strip_whitespace=True, max_length=PERSONA_AGE_MAX_LENGTH)]
Gender = Annotated[str, StringConstraints(strip_whitespace=True, max_length=PERSONA_GENDER_MAX_LENGTH)]
FormOfAddress = Annotated[str, StringConstraints(strip_whitespace=True, max_length=PERSONA_ADDRESS_MAX_LENGTH)]
SpeechExamples = Annotated[str, StringConstraints(max_length=PERSONA_SPEECH_MAX_LENGTH)]
Personality = Annotated[str, StringConstraints(max_length=PERSONA_PERSONALITY_MAX_LENGTH)]

# 고칠 때 null 로 비울 수 있는 칸. 그림은 "없음"이 null 이다. 글의 칸은 빈 글로 비운다
NULLABLE_FIELDS = frozenset({'image_id'})


class PersonaCreate(BaseModel):
    """
    페르소나를 만들 때 받는 값. 이름만 필수다.

    기본인지는 받지 않는다. 처음 만든 것이 기본이 되고, 바꾸려면 기본으로 두는 주소를 부른다.
    """

    # 모르는 칸이 오면 거부한다. owner_id 나 revision 을 끼워 보내도 조용히 무시되지 않고 오류가 난다
    model_config = ConfigDict(extra='forbid')

    name: Name
    description: Description = ''
    image_id: uuid.UUID | None = None
    age: Age = ''
    gender: Gender = ''
    form_of_address: FormOfAddress = ''
    speech_examples: SpeechExamples = ''
    personality: Personality = ''


class PersonaUpdate(BaseModel):
    """
    페르소나를 고칠 때 받는 값. 보낸 칸만 바꾼다.

    보내지 않은 칸은 그대로다. 글의 칸을 비우려면 빈 글을 보낸다. null 은 그림(image_id)만 받는다(그림을 뗀다).
    """

    model_config = ConfigDict(extra='forbid')

    name: Name | None = None
    description: Description | None = None
    image_id: uuid.UUID | None = None
    age: Age | None = None
    gender: Gender | None = None
    form_of_address: FormOfAddress | None = None
    speech_examples: SpeechExamples | None = None
    personality: Personality | None = None

    @model_validator(mode='after')
    def null_only_for_the_image(self) -> Self:
        """글의 칸에 null 을 보내면 거부한다. "비우기"인지 "보내지 않음"인지 헷갈린다."""
        nulls = [name for name in self.model_fields_set - NULLABLE_FIELDS if getattr(self, name) is None]
        if nulls:
            raise ValueError(f'null 로 비울 수 없는 칸입니다(빈 글을 보냅니다): {", ".join(sorted(nulls))}')
        return self

    def changes(self) -> dict:
        """보낸 칸과 그 값."""
        return {name: getattr(self, name) for name in self.model_fields_set}


class PersonaDetail(BaseModel):
    """
    페르소나 하나. 주인만 본다.

    revision 은 내용이 바뀔 때마다 오른다. 세션이 가져간 revision 과 다르면 "새 설정으로 바꾸기"를 보인다.
    """

    id: uuid.UUID
    name: str
    description: str
    image_id: uuid.UUID | None
    age: str
    gender: str
    form_of_address: str
    speech_examples: str
    personality: str
    is_default: bool
    revision: int
    created_at: datetime
    updated_at: datetime
