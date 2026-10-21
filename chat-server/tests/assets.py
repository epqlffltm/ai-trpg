# chat-server/tests/assets.py

"""
테스트가 asset 서버 흉내를 낼 때 쓰는 도구. 앱의 asset 클라이언트(app.state.asset) 자리에 끼운다.

진짜 HTTP 를 거치지 않는다. 주소와 서명은 tests/test_asset_client.py 가 따로 본다.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.assets.client import AssetAdultRequiredError, AssetNotFoundError, AssetUnavailableError
from app.assets.schemas import CharacterCopy, CharacterDocument, PersonaCopy, StartDocument
from app.ratings import Rating

STARTS = [
    StartDocument(title='비 오는 밤', situation='문을 두드리는 소리가 난다.'),
    StartDocument(title='도서관', situation='닫을 시간이 다 됐다.'),
]


def make_character(
    character_id: uuid.UUID | None = None,
    *,
    version: int = 1,
    name: str = '세라',
    greeting: str = '어서 와요. 찾는 책이 있나요?',
    rating: Rating = Rating.ALL,
    starts: list[StartDocument] | None = None,
) -> CharacterCopy:
    """asset 서버가 내주는 캐릭터의 마지막 판."""
    document = CharacterDocument(
        format=1,
        name=name,
        intro_html='<p>도서관의 사서.</p>',
        greeting=greeting,
        speech_examples='"조용히 해 주세요."',
        age='스물넷',
        gender='여성',
        tags=['사서'],
        starts=STARTS if starts is None else starts,
        image_id=uuid.UUID('0b7c6f1e-2d3a-4b5c-8d9e-0f1a2b3c4d5e'),
        rating=rating,
    )
    return CharacterCopy(
        id=character_id or uuid.uuid4(),
        version=version,
        rating=rating,
        published_at=datetime(2026, 10, 21, tzinfo=UTC),
        document=document,
    )


def make_persona(persona_id: uuid.UUID | None = None, *, revision: int = 1, name: str = '한서윤') -> PersonaCopy:
    """asset 서버가 내주는 페르소나의 사본."""
    return PersonaCopy(
        id=persona_id or uuid.uuid4(),
        revision=revision,
        name=name,
        description='출판사에서 일한다.',
        image_id=None,
        age='스물일곱',
        gender='여성',
        form_of_address='선배',
        speech_examples='"그거 진짜야?"',
        personality='호기심이 많다.',
    )


@dataclass
class FakeAsset:
    """
    가짜 asset 서버. characters 와 personas 에 있는 것을 내준다. 없으면 404(AssetNotFoundError)다.

    adult_required 에 넣은 캐릭터는 403, down 이면 모든 요청이 AssetUnavailableError 다.
    무엇을 어느 토큰으로 불렀는지 calls 에 남는다.
    """

    characters: dict[uuid.UUID, CharacterCopy] = field(default_factory=dict)
    personas: dict[uuid.UUID, PersonaCopy] = field(default_factory=dict)
    adult_required: set[uuid.UUID] = field(default_factory=set)
    down: bool = False
    calls: list[tuple[str, uuid.UUID, str]] = field(default_factory=list)

    def add_character(self, copy: CharacterCopy) -> CharacterCopy:
        self.characters[copy.id] = copy
        return copy

    def add_persona(self, copy: PersonaCopy) -> PersonaCopy:
        self.personas[copy.id] = copy
        return copy

    def answer[Copy](self, kind: str, found: dict[uuid.UUID, Copy], wanted: uuid.UUID, token: str) -> Copy:
        self.calls.append((kind, wanted, token))
        if self.down:
            raise AssetUnavailableError('asset 서버가 죽었다(테스트)')
        if wanted in self.adult_required:
            raise AssetAdultRequiredError
        if wanted not in found:
            raise AssetNotFoundError
        return found[wanted]

    async def fetch_character(self, token: str, character_id: uuid.UUID) -> CharacterCopy:
        return self.answer('character', self.characters, character_id, token)

    async def fetch_persona(self, token: str, persona_id: uuid.UUID) -> PersonaCopy:
        return self.answer('persona', self.personas, persona_id, token)
