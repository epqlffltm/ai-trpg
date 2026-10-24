# story-server/app/assets/schemas.py

"""
asset 서버가 내주는 세계관의 판의 모양(asset-server 의 app/worlds/schemas.py 의 WorldCopy,
app/worlds/documents.py 의 WorldDocument). 받은 것을 이 모양으로 검사한 뒤에만 쓴다.
모양이 틀리면 asset 서버를 쓸 수 없는 것으로 본다.

지금은 세션을 만들고 목록에 보이는 데 쓰는 칸(형식, 이름, 등급, 그림)만 검사한다.
나머지 칸(시간대, 지도, 물건, 인물, 이벤트, 엔딩)은 받은 그대로 사본에 남긴다(extra='allow').
그 칸을 쓰는 조각(장면의 인물, 시각, 조건과 효과, 고백과 엔딩)이 그때 읽는 모양을 여기에 더한다.

판의 형식(format)은 asset 서버가 칸을 바꿀 때 올린다. 이 서버가 읽을 줄 아는 형식은 WORLD_FORMAT_MAX 까지다.
  - 1: 초안, 인물, 지도와 물건, 시간대, 보이기
  - 2: 이벤트(조건, 효과, 선택지). 1 의 판은 이벤트가 없다
  - 3: 인물의 고백과 엔딩. 2 까지의 판은 고백과 엔딩이 없다
그보다 새 형식의 판은 받지 않는다. 모르는 규칙(조건, 효과의 종류)을 엔진이 판정할 수 없어서다.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.ratings import Rating

# 이 서버가 읽을 줄 아는 판의 형식의 끝. asset 서버가 형식을 올리면 그것을 읽는 법과 함께 올린다
WORLD_FORMAT_MAX = 3


class WorldDocument(BaseModel):
    """
    판에 굳힌 세계관. 검사하는 칸은 위에 적은 것뿐이고, 나머지 칸은 받은 그대로 둔다.

    사본에는 model_dump 한 것(받은 칸 전부)을 적는다.
    """

    model_config = ConfigDict(extra='allow', frozen=True)

    format: int = Field(ge=1, le=WORLD_FORMAT_MAX)
    name: str
    rating: Rating
    image_id: uuid.UUID | None = None


class WorldCopy(BaseModel):
    """asset 서버가 내주는 세계관의 마지막 판. id 는 asset 서버의 세계관 id 다."""

    model_config = ConfigDict(extra='ignore')

    id: uuid.UUID
    version: int = Field(ge=1)
    rating: Rating
    published_at: datetime
    document: WorldDocument
