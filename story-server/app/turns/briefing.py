# story-server/app/turns/briefing.py

"""
모델에게 알려 줄 판의 칸(이름, 소개, 말투)을 읽는다. DB 도 모델도 모른다.

엔진(app/engine/world.py)은 규칙에 쓰는 칸(id, 조건, 효과)만 읽는다. 글로 보이는 칸은 여기서 따로 읽는다.
엔진이 모델에게 줄 글을 모르게 하려는 것이다. 판의 모양은 asset 서버의 WorldDocument 다
(asset-server 의 app/worlds/documents.py). 모르는 칸은 버린다. 빈 칸은 빈 글로 읽는다.
"""

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict


class Part(BaseModel):
    """판의 칸을 읽는 모양의 공통. 모르는 칸은 버리고 읽은 뒤에는 바꾸지 않는다."""

    model_config = ConfigDict(extra='ignore', frozen=True)


class Named(Part):
    """id 와 이름이 있는 것(시간대, 물건)."""

    id: str
    name: str = ''


class PlaceText(Named):
    """장소의 이름과 설명."""

    description: str = ''


class CharacterText(Part):
    """인물이 가리키는 캐릭터의 판에서 복사한 칸."""

    name: str = ''
    intro_html: str = ''
    speech_examples: str = ''
    age: str = ''
    gender: str = ''


class CastText(Part):
    """인물 하나의 글."""

    id: str
    character: CharacterText = CharacterText()


class Briefing(Part):
    """모델에게 알려 줄 판의 글. 세계관의 이름과 소개, 시간대, 장소, 물건, 인물."""

    name: str = ''
    intro_html: str = ''
    slots: tuple[Named, ...] = ()
    places: tuple[PlaceText, ...] = ()
    items: tuple[Named, ...] = ()
    cast: tuple[CastText, ...] = ()

    def place(self, place_id: str) -> PlaceText | None:
        """그 id 의 장소. 없으면 None."""
        return next((place for place in self.places if place.id == place_id), None)

    def slot_name(self, slot_id: str) -> str:
        """그 id 의 시간대의 이름. 없으면 id 그대로다."""
        return next((slot.name for slot in self.slots if slot.id == slot_id and slot.name), slot_id)

    def item_name(self, item_id: str) -> str:
        """그 id 의 물건의 이름. 없으면 id 그대로다."""
        return next((item.name for item in self.items if item.id == item_id and item.name), item_id)

    def member(self, cast_id: str) -> CastText | None:
        """그 id 의 인물. 없으면 None."""
        return next((member for member in self.cast if member.id == cast_id), None)

    def cast_name(self, cast_id: str) -> str:
        """그 id 의 인물의 이름. 없으면 id 그대로다."""
        member = self.member(cast_id)
        return member.character.name if member is not None and member.character.name else cast_id


def read_briefing(document: Mapping) -> Briefing:
    """판의 문서(사본의 document)를 모델에게 알려 줄 글의 모양으로."""
    return Briefing.model_validate(document)
