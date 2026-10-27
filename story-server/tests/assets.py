# story-server/tests/assets.py

"""
테스트가 asset 서버 흉내를 낼 때 쓰는 도구. 앱의 asset 클라이언트(app.state.asset) 자리에 끼운다.

진짜 HTTP 를 거치지 않는다. 주소와 서명은 tests/test_asset_client.py 가 따로 본다.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.assets.client import AssetAdultRequiredError, AssetNotFoundError, AssetUnavailableError
from app.assets.schemas import PersonaCopy, WorldCopy, WorldDocument
from app.ratings import Rating

IMAGE_ID = uuid.UUID('0b7c6f1e-2d3a-4b5c-8d9e-0f1a2b3c4d5e')


def world_document(name: str = '여름 마을', rating: Rating = Rating.ALL, fmt: int = 3, **fields) -> dict:
    """asset 서버가 굳힌 판의 문서(형식 3 의 칸). fields 로 칸을 덮어쓴다."""
    document = {
        'format': fmt,
        'name': name,
        'intro_html': '<p>바닷가 마을의 여름 방학.</p>',
        'tags': ['일상'],
        'rating': rating,
        'image_id': str(IMAGE_ID),
        'slots': [{'id': 'day', 'name': '낮', 'start_hour': 9}],
        'start_slot': 'day',
        'deadline_days': 30,
        'after_ending': 'end',
        'places': [{'id': 'home', 'name': '집'}],
        'paths': [],
        'start_place': 'home',
        'items': [],
        'start_items': [],
        'cast': [{'id': 'mina', 'character': {'name': '미나'}}],
        'lorebooks': [],
        'events': [{'id': 'meet', 'name': '첫 만남'}],
        'endings': [{'id': 'solo', 'name': '혼자인 여름', 'trigger': {'kind': 'deadline', 'target': None}}],
    }
    document.update(fields)
    return document


def make_world(
    world_id: uuid.UUID | None = None,
    *,
    version: int = 1,
    name: str = '여름 마을',
    rating: Rating = Rating.ALL,
    fields: dict | None = None,
) -> WorldCopy:
    """asset 서버가 내주는 세계관의 마지막 판. fields 로 문서의 칸을 덮어쓴다."""
    return WorldCopy(
        id=world_id or uuid.uuid4(),
        version=version,
        rating=rating,
        published_at=datetime(2026, 10, 24, tzinfo=UTC),
        document=WorldDocument.model_validate(world_document(name, rating, **(fields or {}))),
    )


def make_persona(
    persona_id: uuid.UUID | None = None, *, revision: int = 1, name: str = '하루', **fields
) -> PersonaCopy:
    """asset 서버가 내주는 계정 페르소나의 사본. fields 로 칸을 덮어쓴다."""
    body = {
        'id': persona_id or uuid.uuid4(),
        'revision': revision,
        'name': name,
        'description': '전학 온 학생.',
        'image_id': None,
        'age': '17',
        'gender': '',
        'form_of_address': '하루야',
        'speech_examples': '',
        'personality': '조용하다.',
    }
    return PersonaCopy.model_validate({**body, **fields})


@dataclass
class FakeAsset:
    """
    가짜 asset 서버. worlds 와 personas 에 있는 것을 내준다. 없으면 404(AssetNotFoundError)다.

    adult_required 에 넣은 세계관은 403, down 이면 모든 요청이 AssetUnavailableError 다.
    무엇을 어느 토큰으로 불렀는지 calls 에 남는다.
    """

    worlds: dict[uuid.UUID, WorldCopy] = field(default_factory=dict)
    personas: dict[uuid.UUID, PersonaCopy] = field(default_factory=dict)
    adult_required: set[uuid.UUID] = field(default_factory=set)
    down: bool = False
    calls: list[tuple[uuid.UUID, str]] = field(default_factory=list)

    def add_world(self, copy: WorldCopy) -> WorldCopy:
        self.worlds[copy.id] = copy
        return copy

    def add_persona(self, copy: PersonaCopy) -> PersonaCopy:
        self.personas[copy.id] = copy
        return copy

    async def fetch_persona(self, token: str, persona_id: uuid.UUID) -> PersonaCopy:
        self.calls.append((persona_id, token))
        if self.down:
            raise AssetUnavailableError('asset 서버가 죽었다(테스트)')
        if persona_id not in self.personas:
            raise AssetNotFoundError
        return self.personas[persona_id]

    async def fetch_world(self, token: str, world_id: uuid.UUID) -> WorldCopy:
        self.calls.append((world_id, token))
        if self.down:
            raise AssetUnavailableError('asset 서버가 죽었다(테스트)')
        if world_id in self.adult_required:
            raise AssetAdultRequiredError
        if world_id not in self.worlds:
            raise AssetNotFoundError
        return self.worlds[world_id]
