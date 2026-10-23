# chat-server/app/assets/schemas.py

"""
asset 서버가 내주는 것의 모양(asset-server 의 app/characters/schemas.py 의 CharacterCopy, app/personas/schemas.py 의
PersonaCopy). 받은 것을 이 모양으로 검사한 뒤에만 쓴다. 모양이 틀리면 asset 서버를 쓸 수 없는 것으로 본다.

모르는 칸은 버린다. asset 서버가 칸을 더해도 chat 이 멈추지 않는다. 그래서 판의 사본에 남기려는 칸은 여기에 적어야 한다.
판의 형식(format)은 받은 그대로 적어 둔다. 칸이 바뀌면 asset 서버가 번호를 올리고, 이쪽은 번호로 읽는 법을 고른다.
  - 1: 처음의 칸
  - 2: 지도(장소, 길, 처음 있는 장소)와 물건(물건, 시작 소지품). 형식 1 의 판에서는 비어 있다.
       쓰는 것(현재 장소, 이동, 소지품)은 chat 의 만드는 순서 5(장소와 소지품)다
  - 3: 호감도(보이는 방식, 시작 값, 단계, 오르내리는 규칙). 형식 1, 2 의 판에서는 없다(null)
  - 4: 시작 상황의 시작 시각(hour)과 장소의 시간대 배경(backgrounds). 3 까지의 판은 정오에 시작하고 시간대 배경이 없다
  - 5: 일러스트(그림, 해금 대상인지, 장면의 설명, 나오는 조건, #669). 4 까지의 판은 일러스트가 없다
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.ratings import Rating

# 시작 시각을 적지 않은 시작 상황(형식 3 까지의 판)은 정오에 시작한다(asset 서버의 START_HOUR_DEFAULT 와 같다)
START_HOUR_DEFAULT = 12


class StartDocument(BaseModel):
    """시작 상황 하나. 제목은 목록에, 상황은 모델에 간다. hour 는 시작하는 시각(몇 시, 0~23)이다."""

    model_config = ConfigDict(extra='ignore')

    title: str
    situation: str
    hour: int = START_HOUR_DEFAULT


class PlaceDocument(BaseModel):
    """
    장소 하나. id 는 캐릭터 안에서 고유하다. 그림(image_id)은 그 장소의 기본 배경이다.
    backgrounds 는 시간대(dawn, morning, day, evening, night)마다의 배경이다.
    모르는 시간대도 받아 둔다(쓰이지 않을 뿐이다).
    """

    model_config = ConfigDict(extra='ignore')

    id: str
    name: str
    description: str
    image_id: uuid.UUID | None
    backgrounds: dict[str, uuid.UUID] = {}


class PathDocument(BaseModel):
    """두 장소(a, b) 사이의 길. 양쪽으로 다닌다. minutes 는 걸리는 시간(분)이다."""

    model_config = ConfigDict(extra='ignore')

    a: str
    b: str
    minutes: int


class ItemDocument(BaseModel):
    """
    물건 하나. kind 는 thing 이나 clothing(건네면 상대의 차림에 들어간다)이다. 모르는 종류도 받아 둔다.
    consumable 이면 쓰면 하나 없어진다.
    """

    model_config = ConfigDict(extra='ignore')

    id: str
    name: str
    description: str
    kind: str
    consumable: bool = False
    image_id: uuid.UUID | None


class StartItemDocument(BaseModel):
    """사용자가 처음에 가진 물건(item 은 물건의 id)과 그 수."""

    model_config = ConfigDict(extra='ignore')

    item: str
    count: int


class StageDocument(BaseModel):
    """호감도의 단계 하나. at 이상이면 이 단계다."""

    model_config = ConfigDict(extra='ignore')

    name: str
    at: int


class TriggerDocument(BaseModel):
    """
    호감도를 바꾸는 행동. kind 는 give_item, reach_place, use_item 이다.
    모르는 종류도 받아 둔다(맞는 행동이 없을 뿐이다).
    """

    model_config = ConfigDict(extra='ignore')

    kind: str
    target: str


class AffectionRuleDocument(BaseModel):
    """오르내리는 규칙 하나. on 의 행동을 하면 change 만큼. once 면 그 가지에서 처음 한 번만."""

    model_config = ConfigDict(extra='ignore')

    id: str
    on: TriggerDocument
    change: int
    once: bool = False


class AffectionDocument(BaseModel):
    """캐릭터의 호감도. display 는 number(숫자와 게이지)나 stage(단계 이름과 게이지, 숫자를 내려보내지 않는다)다."""

    model_config = ConfigDict(extra='ignore')

    display: str
    start: int
    stages: list[StageDocument]
    rules: list[AffectionRuleDocument] = []


class IllustrationConditionDocument(BaseModel):
    """
    일러스트가 나오는 조건. kind 는 reach_place(장소의 id), give_item(물건의 id), affection_stage(단계의 이름)다.
    모르는 종류도 받아 둔다(맞는 일이 없을 뿐이다).
    """

    model_config = ConfigDict(extra='ignore')

    kind: str
    target: str


class IllustrationDocument(BaseModel):
    """일러스트 하나. collectible 이면 해금 대상이다. scene 은 그 답을 쓸 때 모델이 읽는 장면의 설명이다."""

    model_config = ConfigDict(extra='ignore')

    id: str
    title: str
    image_id: uuid.UUID
    scene: str = ''
    collectible: bool = True
    when: IllustrationConditionDocument


class CharacterDocument(BaseModel):
    """판에 굳힌 캐릭터. intro_html 은 asset 서버가 허용 목록으로 거른 소개다."""

    model_config = ConfigDict(extra='ignore')

    format: int
    name: str
    intro_html: str
    greeting: str
    speech_examples: str
    age: str
    gender: str
    tags: list[str]
    starts: list[StartDocument]
    image_id: uuid.UUID | None
    rating: Rating
    places: list[PlaceDocument] = []
    paths: list[PathDocument] = []
    start_place: str | None = None
    items: list[ItemDocument] = []
    start_items: list[StartItemDocument] = []
    affection: AffectionDocument | None = None
    illustrations: list[IllustrationDocument] = []


class CharacterCopy(BaseModel):
    """asset 서버의 마지막 판. id 는 asset 서버의 캐릭터 id 다."""

    model_config = ConfigDict(extra='ignore')

    id: uuid.UUID
    version: int
    rating: Rating
    published_at: datetime
    document: CharacterDocument


class PersonaCopy(BaseModel):
    """asset 서버의 계정 페르소나의 사본. id 는 asset 서버의 페르소나 id 다."""

    model_config = ConfigDict(extra='ignore')

    id: uuid.UUID
    revision: int
    name: str
    description: str
    image_id: uuid.UUID | None
    age: str
    gender: str
    form_of_address: str
    speech_examples: str
    personality: str
