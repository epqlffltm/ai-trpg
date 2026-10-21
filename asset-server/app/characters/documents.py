# asset-server/app/characters/documents.py

"""
캐릭터의 판에 굳히는 문서의 모양(#567). chat 이 대화를 시작할 때 이 문서를 가져가 복사한다.

판의 형식(format)에 번호를 둔다. 칸이 늘면(호감도, 의복과 물건, 지도) 번호를 올리고, 받는 쪽은 번호로 읽는 법을 고른다.
TRPG 의 판 형식과 같은 방식이다. 지금은 1 이다.
DB 를 모르는 순수한 함수다. 초안(Character)과 거른 소개에서 문서를 만든다.
"""

import uuid

from pydantic import BaseModel, ConfigDict

from app.characters.models import Character
from app.ratings import Rating

# 판의 형식. 칸을 바꾸면 올린다
DOCUMENT_FORMAT = 1


class StartDocument(BaseModel):
    """시작 상황 하나."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    title: str
    situation: str


class CharacterDocument(BaseModel):
    """판에 굳힌 캐릭터. intro_html 은 허용 목록으로 거른 소개다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

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


def build_document(character: Character, cleaned_intro: str) -> CharacterDocument:
    """초안과 거른 소개로 판의 문서를 만든다."""
    return CharacterDocument(
        format=DOCUMENT_FORMAT,
        name=character.name,
        intro_html=cleaned_intro,
        greeting=character.greeting,
        speech_examples=character.speech_examples,
        age=character.age,
        gender=character.gender,
        tags=list(character.tags),
        starts=[StartDocument(**start) for start in character.starts],
        image_id=character.image_id,
        rating=Rating(character.rating),
    )
