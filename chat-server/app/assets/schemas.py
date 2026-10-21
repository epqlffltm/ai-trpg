# chat-server/app/assets/schemas.py

"""
asset 서버가 내주는 것의 모양(asset-server 의 app/characters/schemas.py 의 CharacterCopy, app/personas/schemas.py 의
PersonaCopy). 받은 것을 이 모양으로 검사한 뒤에만 쓴다. 모양이 틀리면 asset 서버를 쓸 수 없는 것으로 본다.

모르는 칸은 버린다. asset 서버가 칸을 더해도 chat 이 멈추지 않는다.
판의 형식(format)은 받은 그대로 적어 둔다. 칸이 바뀌면 asset 서버가 번호를 올리고, 이쪽은 번호로 읽는 법을 고른다.
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
