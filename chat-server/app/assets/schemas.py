# chat-server/app/assets/schemas.py

"""
asset 서버가 내주는 것의 모양(asset-server 의 app/characters/schemas.py 의 CharacterCopy, app/personas/schemas.py 의
PersonaCopy). 받은 것을 이 모양으로 검사한 뒤에만 쓴다. 모양이 틀리면 asset 서버를 쓸 수 없는 것으로 본다.

모르는 칸은 버린다. asset 서버가 칸을 더해도 chat 이 멈추지 않는다. 그래서 판의 사본에 남기려는 칸은 여기에 적어야 한다.
판의 형식(format)은 받은 그대로 적어 둔다. 칸이 바뀌면 asset 서버가 번호를 올리고, 이쪽은 번호로 읽는 법을 고른다.
  - 1: 처음의 칸
  - 2: 지도(장소, 길, 처음 있는 장소)와 물건(물건, 시작 소지품). 형식 1 의 판에서는 비어 있다.
       쓰는 것(현재 장소, 이동, 소지품)은 chat 의 만드는 순서 5(장소와 소지품)다
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.ratings import Rating


class StartDocument(BaseModel):
    """시작 상황 하나. 제목은 목록에, 상황은 모델에 간다."""

    model_config = ConfigDict(extra='ignore')

    title: str
    situation: str


class PlaceDocument(BaseModel):
    """장소 하나. id 는 캐릭터 안에서 고유하다. 그림은 그 장소의 배경이다."""

    model_config = ConfigDict(extra='ignore')

    id: str
    name: str
    description: str
    image_id: uuid.UUID | None


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
