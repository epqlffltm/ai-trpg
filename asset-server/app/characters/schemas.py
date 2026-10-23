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
    AFFECTION_MAX,
    AFFECTION_MAX_CHANGE,
    AFFECTION_MAX_RULES,
    AFFECTION_MAX_STAGES,
    CHARACTER_AGE_MAX_LENGTH,
    CHARACTER_GENDER_MAX_LENGTH,
    CHARACTER_GREETING_MAX_LENGTH,
    CHARACTER_MAX_ILLUSTRATIONS,
    CHARACTER_MAX_ITEMS,
    CHARACTER_MAX_PATHS,
    CHARACTER_MAX_PLACES,
    CHARACTER_MAX_START_ITEMS,
    CHARACTER_MAX_STARTS,
    CHARACTER_MAX_TAGS,
    CHARACTER_NAME_MAX_LENGTH,
    CHARACTER_SPEECH_MAX_LENGTH,
    CHARACTER_TAG_MAX_LENGTH,
    HOURS_PER_DAY,
    ILLUSTRATION_SCENE_MAX_LENGTH,
    ILLUSTRATION_TITLE_MAX_LENGTH,
    ITEM_DESCRIPTION_MAX_LENGTH,
    ITEM_NAME_MAX_LENGTH,
    KEY_MAX_LENGTH,
    KEY_PATTERN,
    PATH_MAX_MINUTES,
    PLACE_DESCRIPTION_MAX_LENGTH,
    PLACE_NAME_MAX_LENGTH,
    STAGE_NAME_MAX_LENGTH,
    START_HOUR_DEFAULT,
    START_ITEM_MAX_COUNT,
    START_SITUATION_MAX_LENGTH,
    START_TITLE_MAX_LENGTH,
    VERSION_NOTE_MAX_LENGTH,
    AffectionDisplay,
    IllustrationWhen,
    ItemKind,
    TimeOfDay,
    TriggerKind,
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
    """
    시작 상황 하나. 대화를 열 때 사용자가 고른다. 제목은 목록에, 상황은 모델에 간다.
    hour 는 대화가 시작하는 시각(몇 시)이다. 1일째의 그 시각에서 시작해 이동과 시간 보내기로 흐른다(chat).
    """

    model_config = ConfigDict(extra='forbid')

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=START_TITLE_MAX_LENGTH)]
    situation: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=START_SITUATION_MAX_LENGTH)
    ]
    hour: Annotated[int, Field(ge=0, lt=HOURS_PER_DAY)] = START_HOUR_DEFAULT


def reject_repeated_starts(starts: list[Start]) -> list[Start]:
    """제목이 같은 시작 상황이 둘이면 거부한다. 목록에서 고를 수 없다."""
    reject_repeated([start.title for start in starts])
    return starts


Starts = Annotated[list[Start], Field(max_length=CHARACTER_MAX_STARTS), AfterValidator(reject_repeated_starts)]

# 장소와 물건의 id. 캐릭터 안에서 고유하다. 대소문자는 가린다(만드는 화면이 붙이는 것이라 헷갈릴 일이 적다)
Key = Annotated[str, StringConstraints(min_length=1, max_length=KEY_MAX_LENGTH, pattern=KEY_PATTERN)]


class Place(BaseModel):
    """
    장소 하나(지도의 점). 그림(image_id)은 그 장소의 기본 배경이다. 설명은 모델이 읽는다.
    backgrounds 는 시간대마다의 배경이다. 그 시간대의 것이 없으면 기본 배경을 쓴다(chat 의 화면).
    """

    model_config = ConfigDict(extra='forbid')

    id: Key
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=PLACE_NAME_MAX_LENGTH)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=PLACE_DESCRIPTION_MAX_LENGTH)] = ''
    image_id: uuid.UUID | None = None
    backgrounds: dict[TimeOfDay, uuid.UUID] = {}


class Path(BaseModel):
    """두 장소(a, b) 사이의 길. 양쪽으로 다닌다. minutes 는 걸리는 시간(분)이고 그만큼 시각이 흐른다."""

    model_config = ConfigDict(extra='forbid')

    a: Key
    b: Key
    minutes: Annotated[int, Field(ge=0, le=PATH_MAX_MINUTES)]

    @model_validator(mode='after')
    def two_places(self) -> Self:
        """제자리로 가는 길은 없다."""
        if self.a == self.b:
            raise ValueError('길은 서로 다른 두 장소를 잇습니다.')
        return self


class Item(BaseModel):
    """물건 하나. 옷(clothing)은 건네면 상대의 차림에 들어간다. consumable 이면 쓰면 하나 없어진다."""

    model_config = ConfigDict(extra='forbid')

    id: Key
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=ITEM_NAME_MAX_LENGTH)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=ITEM_DESCRIPTION_MAX_LENGTH)] = ''
    kind: ItemKind = ItemKind.THING
    # 쓰면 하나 없어지는가(음식은 참, 우산은 거짓). chat 이 쓰기에서 소지품을 줄일 때 본다
    consumable: bool = False
    image_id: uuid.UUID | None = None


class StartItem(BaseModel):
    """사용자가 처음에 가진 물건(item 은 물건의 id)과 그 수."""

    model_config = ConfigDict(extra='forbid')

    item: Key
    count: Annotated[int, Field(ge=1, le=START_ITEM_MAX_COUNT)] = 1


def reject_repeated_keys(keys: list[str]) -> None:
    """같은 id 가 두 번 있으면 거부한다. 길과 소지품이 어느 것을 가리키는지 모른다."""
    if len(set(keys)) != len(keys):
        raise ValueError('같은 id 가 두 번 있습니다.')


def unique_places(places: list[Place]) -> list[Place]:
    reject_repeated_keys([place.id for place in places])
    return places


def unique_paths(paths: list[Path]) -> list[Path]:
    """같은 두 장소를 잇는 길은 하나다(a, b 의 차례는 가리지 않는다)."""
    pairs = [frozenset((path.a, path.b)) for path in paths]
    if len(set(pairs)) != len(pairs):
        raise ValueError('같은 두 장소를 잇는 길이 두 번 있습니다.')
    return paths


def unique_items(items: list[Item]) -> list[Item]:
    reject_repeated_keys([item.id for item in items])
    return items


def unique_start_items(starts: list[StartItem]) -> list[StartItem]:
    """같은 물건은 한 줄에 수로 적는다."""
    reject_repeated_keys([start.item for start in starts])
    return starts


Places = Annotated[list[Place], Field(max_length=CHARACTER_MAX_PLACES), AfterValidator(unique_places)]
Paths = Annotated[list[Path], Field(max_length=CHARACTER_MAX_PATHS), AfterValidator(unique_paths)]
Items = Annotated[list[Item], Field(max_length=CHARACTER_MAX_ITEMS), AfterValidator(unique_items)]
StartItems = Annotated[list[StartItem], Field(max_length=CHARACTER_MAX_START_ITEMS), AfterValidator(unique_start_items)]


class Stage(BaseModel):
    """호감도의 단계 하나. at 이상이면 이 단계다(다음 단계의 at 전까지)."""

    model_config = ConfigDict(extra='forbid')

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=STAGE_NAME_MAX_LENGTH)]
    at: Annotated[int, Field(ge=0, le=AFFECTION_MAX)]


class Trigger(BaseModel):
    """호감도를 바꾸는 사용자의 행동. target 은 그 물건이나 장소의 id 다."""

    model_config = ConfigDict(extra='forbid')

    kind: TriggerKind
    target: Key


class AffectionRule(BaseModel):
    """
    오르내리는 규칙 하나. on 의 행동을 하면 change 만큼 바꾼다(0~100 안으로 자른다).
    once 면 그 가지에서 처음 한 번만 바꾼다(처음 하는 일). id 는 캐릭터 안에서 고유하고, chat 이 "이미 했다"를 적는다.
    """

    model_config = ConfigDict(extra='forbid')

    id: Key
    on: Trigger
    change: Annotated[int, Field(ge=-AFFECTION_MAX_CHANGE, le=AFFECTION_MAX_CHANGE)]
    once: bool = False

    @model_validator(mode='after')
    def changes_something(self) -> Self:
        """바꾸지 않는 규칙은 없다."""
        if self.change == 0:
            raise ValueError('규칙은 호감도를 바꿉니다(0 이 아닙니다).')
        return self


def stages_from_zero(stages: list[Stage]) -> list[Stage]:
    """첫 단계는 0 에서 시작하고 경계가 오른다. 같은 이름은 없다. 어느 값이든 단계가 하나다."""
    if stages[0].at != 0:
        raise ValueError('첫 단계는 0 에서 시작합니다.')
    if any(later.at <= earlier.at for earlier, later in zip(stages, stages[1:], strict=False)):
        raise ValueError('단계의 경계는 차례로 커집니다.')
    reject_repeated([stage.name for stage in stages])
    return stages


def unique_rules(rules: list[AffectionRule]) -> list[AffectionRule]:
    reject_repeated_keys([rule.id for rule in rules])
    return rules


class Affection(BaseModel):
    """
    캐릭터의 호감도. 값 하나(0~100)와 단계들이다. display 는 사람에게 보이는 방식이다
    (number: 숫자와 게이지, stage: 단계 이름과 게이지. 숫자는 chat 이 내려보내지 않는다).
    """

    model_config = ConfigDict(extra='forbid')

    display: AffectionDisplay = AffectionDisplay.NUMBER
    start: Annotated[int, Field(ge=0, le=AFFECTION_MAX)] = 0
    stages: Annotated[
        list[Stage], Field(min_length=1, max_length=AFFECTION_MAX_STAGES), AfterValidator(stages_from_zero)
    ]
    rules: Annotated[list[AffectionRule], Field(max_length=AFFECTION_MAX_RULES), AfterValidator(unique_rules)] = []


class IllustrationCondition(BaseModel):
    """일러스트가 나오는 조건. target 은 장소나 물건의 id, 또는 호감도 단계의 이름이다."""

    model_config = ConfigDict(extra='forbid')

    kind: IllustrationWhen
    target: Annotated[str, StringConstraints(min_length=1, max_length=KEY_MAX_LENGTH)]


class Illustration(BaseModel):
    """
    일러스트 하나(#669). 조건이 맞은 뒤의 첫 응답에 붙어 배경과 캐릭터를 대신한다(chat).
    collectible 이면 해금 대상이다. 한 번 열면 계정에 남고 갤러리와 소개의 칸에 보인다.
    아니면 이야기 중에만 나온다(칸도 보이지 않는다). scene 은 그 답을 쓸 때 모델이 읽는 장면의 설명이다.
    """

    model_config = ConfigDict(extra='forbid')

    id: Key
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=ILLUSTRATION_TITLE_MAX_LENGTH)
    ]
    image_id: uuid.UUID
    scene: Annotated[str, StringConstraints(strip_whitespace=True, max_length=ILLUSTRATION_SCENE_MAX_LENGTH)] = ''
    collectible: bool = True
    when: IllustrationCondition


def unique_illustrations(illustrations: list[Illustration]) -> list[Illustration]:
    reject_repeated_keys([illustration.id for illustration in illustrations])
    return illustrations


Illustrations = Annotated[
    list[Illustration], Field(max_length=CHARACTER_MAX_ILLUSTRATIONS), AfterValidator(unique_illustrations)
]

# 지도와 물건, 일러스트의 칸. DB 에 적을 때 dict 의 목록으로 바꾼다
WORLD_LISTS = ('places', 'paths', 'items', 'start_items', 'illustrations')


def attached_images(
    image_id: uuid.UUID | None, places: list[Place], items: list[Item], illustrations: list[Illustration]
) -> list[uuid.UUID]:
    """붙인 그림들. 대표 그림, 장소의 배경(기본과 시간대마다), 물건의 그림, 일러스트다. 없는 것은 뺀다."""
    found = [image_id] if image_id is not None else []
    found += [entry.image_id for entry in [*places, *items] if entry.image_id is not None]
    found += [background for place in places for background in place.backgrounds.values()]
    return found + [illustration.image_id for illustration in illustrations]


# 고칠 때 null 로 비울 수 있는 칸. 그림, 처음 있는 장소, 호감도는 "없음"이 null 이다. 글과 목록의 칸은 빈 값으로 비운다
NULLABLE_FIELDS = frozenset({'image_id', 'start_place', 'affection'})


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
    places: Places = []
    paths: Paths = []
    start_place: Key | None = None
    items: Items = []
    start_items: StartItems = []
    affection: Affection | None = None
    illustrations: Illustrations = []

    def image_ids(self) -> list[uuid.UUID]:
        """붙인 그림들. 자기 그림인지 볼 것들이다."""
        return attached_images(self.image_id, self.places, self.items, self.illustrations)

    def values(self) -> dict:
        """DB 에 적을 칸과 값. 시작 상황, 지도, 물건은 dict 의 목록이다(그림의 id 는 글이다)."""
        values = self.model_dump()
        for name in ('starts', *WORLD_LISTS):
            values[name] = [entry.model_dump(mode='json') for entry in getattr(self, name)]
        values['affection'] = self.affection.model_dump(mode='json') if self.affection is not None else None
        return values


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
    places: Places | None = None
    paths: Paths | None = None
    start_place: Key | None = None
    items: Items | None = None
    start_items: StartItems | None = None
    affection: Affection | None = None
    illustrations: Illustrations | None = None

    @model_validator(mode='after')
    def null_only_for_the_image(self) -> Self:
        """그림, 처음 있는 장소, 호감도 말고는 null 을 거부한다. "비우기"인지 "보내지 않음"인지 헷갈린다."""
        nulls = [name for name in self.model_fields_set - NULLABLE_FIELDS if getattr(self, name) is None]
        if nulls:
            raise ValueError(f'null 로 비울 수 없는 칸입니다: {", ".join(sorted(nulls))}')
        return self

    def changes(self) -> dict:
        """보낸 칸과 그 값. 시작 상황, 지도, 물건은 DB 에 적을 모양(dict 의 목록)으로 바꾼다."""
        changes = {name: getattr(self, name) for name in self.model_fields_set}
        for name in ('starts', *WORLD_LISTS):
            if name in changes:
                changes[name] = [entry.model_dump(mode='json') for entry in changes[name]]
        if changes.get('affection') is not None:
            changes['affection'] = self.affection.model_dump(mode='json')
        return changes

    def image_ids(self) -> list[uuid.UUID]:
        """보낸 칸에 붙인 그림들. 자기 그림인지 볼 것들이다."""
        return attached_images(self.image_id, self.places or [], self.items or [], self.illustrations or [])


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
    places: list[Place]
    paths: list[Path]
    start_place: str | None
    items: list[Item]
    start_items: list[StartItem]
    affection: Affection | None
    illustrations: list[Illustration]
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
