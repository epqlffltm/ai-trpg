# asset-server/app/characters/schemas.py

"""
캐릭터 API 가 받는 입력과 내보내는 응답의 모양(#567).

길이는 모델의 상수를 그대로 쓴다. DB 의 CHECK 는 마지막 방어선이고, 어느 칸이 왜 틀렸는지 알려 주는 것은 이쪽이다.
"""

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.characters.documents import CharacterDocument
from app.characters.models import (
    CHARACTER_AGE_MAX_LENGTH,
    CHARACTER_GENDER_MAX_LENGTH,
    CHARACTER_GREETING_MAX_LENGTH,
    CHARACTER_MAX_STARTS,
    CHARACTER_MAX_TAGS,
    CHARACTER_NAME_MAX_LENGTH,
    CHARACTER_SPEECH_MAX_LENGTH,
    CHARACTER_TAG_MAX_LENGTH,
    START_SITUATION_MAX_LENGTH,
    START_TITLE_MAX_LENGTH,
    VERSION_NOTE_MAX_LENGTH,
    Visibility,
)
from app.content.html import INTRO_MAX_BYTES, RemovedKind, intro_too_long
from app.ratings import Rating


def fits_intro_size(html: str) -> str:
    """소개가 크기 상한(50KB, UTF-8 의 바이트)을 넘으면 거부한다."""
    if intro_too_long(html):
        raise ValueError(f'소개는 {INTRO_MAX_BYTES // 1024}KB 까지 쓸 수 있습니다.')
    return html


def reject_repeated(names: list[str]) -> list[str]:
    """같은 것이 두 번 있으면 거부한다. 대소문자만 다른 것도 같은 것으로 본다."""
    folded = [name.casefold() for name in names]
    if len(set(folded)) != len(folded):
        raise ValueError('같은 것이 두 번 있습니다.')
    return names


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=CHARACTER_NAME_MAX_LENGTH)]
Intro = Annotated[str, AfterValidator(fits_intro_size)]
Greeting = Annotated[str, StringConstraints(max_length=CHARACTER_GREETING_MAX_LENGTH)]
SpeechExamples = Annotated[str, StringConstraints(max_length=CHARACTER_SPEECH_MAX_LENGTH)]
Age = Annotated[str, StringConstraints(strip_whitespace=True, max_length=CHARACTER_AGE_MAX_LENGTH)]
Gender = Annotated[str, StringConstraints(strip_whitespace=True, max_length=CHARACTER_GENDER_MAX_LENGTH)]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=CHARACTER_TAG_MAX_LENGTH)]
Tags = Annotated[list[Tag], Field(max_length=CHARACTER_MAX_TAGS), AfterValidator(reject_repeated)]


class Start(BaseModel):
    """시작 상황 하나. 대화를 열 때 사용자가 고른다. 제목은 목록에, 상황은 모델에 간다."""

    model_config = ConfigDict(extra='forbid')

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=START_TITLE_MAX_LENGTH)]
    situation: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=START_SITUATION_MAX_LENGTH)
    ]


def reject_repeated_starts(starts: list[Start]) -> list[Start]:
    """제목이 같은 시작 상황이 둘이면 거부한다. 목록에서 고를 수 없다."""
    reject_repeated([start.title for start in starts])
    return starts


Starts = Annotated[list[Start], Field(max_length=CHARACTER_MAX_STARTS), AfterValidator(reject_repeated_starts)]

# 고칠 때 null 로 비울 수 있는 칸. 그림은 "없음"이 null 이다. 글과 목록의 칸은 빈 값으로 비운다
NULLABLE_FIELDS = frozenset({'image_id'})


class CharacterCreate(BaseModel):
    """캐릭터를 만들 때 받는 값. 이름만 필수다. 처음에는 비공개다."""

    model_config = ConfigDict(extra='forbid')

    name: Name
    intro_html: Intro = ''
    greeting: Greeting = ''
    speech_examples: SpeechExamples = ''
    age: Age = ''
    gender: Gender = ''
    tags: Tags = []
    starts: Starts = []
    image_id: uuid.UUID | None = None
    rating: Rating = Rating.ALL


class CharacterUpdate(BaseModel):
    """
    캐릭터를 고칠 때 받는 값. 보낸 칸만 바꾼다. 초안만 바뀐다. 게시한 판은 그대로다.

    null 은 그림(image_id)만 받는다. 공개 범위(visibility)도 여기서 바꾼다(공개는 운영자만, 1~2단계).
    """

    model_config = ConfigDict(extra='forbid')

    name: Name | None = None
    intro_html: Intro | None = None
    greeting: Greeting | None = None
    speech_examples: SpeechExamples | None = None
    age: Age | None = None
    gender: Gender | None = None
    tags: Tags | None = None
    starts: Starts | None = None
    image_id: uuid.UUID | None = None
    rating: Rating | None = None
    visibility: Visibility | None = None

    @model_validator(mode='after')
    def null_only_for_the_image(self) -> Self:
        """그림 말고는 null 을 거부한다. "비우기"인지 "보내지 않음"인지 헷갈린다."""
        nulls = [name for name in self.model_fields_set - NULLABLE_FIELDS if getattr(self, name) is None]
        if nulls:
            raise ValueError(f'null 로 비울 수 없는 칸입니다: {", ".join(sorted(nulls))}')
        return self

    def changes(self) -> dict:
        """보낸 칸과 그 값. 시작 상황은 DB 에 적을 모양(dict)으로 바꾼다."""
        changes = {name: getattr(self, name) for name in self.model_fields_set}
        if 'starts' in changes:
            changes['starts'] = [start.model_dump() for start in self.starts or []]
        return changes


class CharacterDetail(BaseModel):
    """캐릭터의 초안 하나. 만든 사람만 본다. latest_version 은 마지막으로 게시한 판의 번호다(없으면 null)."""

    id: uuid.UUID
    name: str
    intro_html: str
    greeting: str
    speech_examples: str
    age: str
    gender: str
    tags: list[str]
    starts: list[Start]
    image_id: uuid.UUID | None
    rating: Rating
    visibility: Visibility
    latest_version: int | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CharacterSummary(BaseModel):
    """내 캐릭터 목록의 한 줄."""

    id: uuid.UUID
    name: str
    rating: Rating
    visibility: Visibility
    latest_version: int | None
    updated_at: datetime


class CharacterPage(BaseModel):
    """목록의 한 쪽과 전체 개수."""

    items: list[CharacterSummary]
    total: int


class VersionCreate(BaseModel):
    """게시할 때 받는 값. 이번 판에서 무엇이 바뀌었는지 적는다(비워도 된다)."""

    model_config = ConfigDict(extra='forbid')

    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=VERSION_NOTE_MAX_LENGTH)] = ''


class VersionSummary(BaseModel):
    """판의 목록에 싣는 값. 굳힌 문서는 싣지 않는다."""

    id: uuid.UUID
    number: int
    note: str
    created_at: datetime


class VersionDetail(VersionSummary):
    """판 하나. 굳힌 문서까지 싣는다."""

    document: CharacterDocument


class RemovedItem(BaseModel):
    """게시할 때 소개에서 걸러 낸 것 하나(app/content/html.py)."""

    kind: RemovedKind
    name: str


class PublishResult(VersionDetail):
    """
    게시한 결과. 새 판과, 소개에서 걸러 낸 것들(removed)이다.

    걸러 낸 것이 있어도 게시는 된다. 거른 소개가 판에 들어간다. 화면이 removed 를 제작자에게 보인다.
    """

    removed: list[RemovedItem]


class PublishCheck(BaseModel):
    """
    지금 게시하면 막히는 이유와 걸러질 것. 판을 만들지 않는다.

    problems 는 게시가 409 로 돌려주는 것과 같은 이름이다. 비어 있으면 게시할 수 있다(ready).
    """

    ready: bool
    problems: list[str]
    removed: list[RemovedItem]


class PublicCharacterSummary(BaseModel):
    """공개 목록의 한 줄. 마지막 판의 값이다."""

    id: uuid.UUID
    version: int
    name: str
    tags: list[str]
    rating: Rating
    image_id: uuid.UUID | None
    published_at: datetime


class PublicCharacterPage(BaseModel):
    """공개 목록의 한 쪽과 전체 개수."""

    items: list[PublicCharacterSummary]
    total: int


class PublicCharacterDetail(BaseModel):
    """공개 캐릭터 하나. 마지막 판의 문서다."""

    id: uuid.UUID
    version: int
    published_at: datetime
    document: CharacterDocument


class CharacterCopy(BaseModel):
    """
    다른 서버(chat, story)에 내주는 판. 대화를 시작할 때 가져가 고정한다.

    마지막 판의 번호와 문서다. 가져간 쪽은 번호를 적어 두고,
    지금의 번호(CharacterVersionNumber)가 크면 "새 판이 있다"를 알린다.
    """

    id: uuid.UUID
    version: int
    rating: Rating
    published_at: datetime
    document: CharacterDocument


class CharacterVersionNumber(BaseModel):
    """캐릭터의 지금 판 번호. 화면을 열 때 한 번 묻는다. 문서는 싣지 않는다."""

    id: uuid.UUID
    version: int
