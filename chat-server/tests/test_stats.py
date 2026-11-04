# chat-server/tests/test_stats.py

"""
asset 서버가 캐릭터마다 대화 시작 수를 받아 가는 주소(app/stats/, #985)를 검증한다. 실제 DB(chat_test)에서 돈다.

  - 사본의 원본 id(asset 서버의 id)마다 모든 수와 최근 7일의 수다. 판이 여럿이어도, 사람이 여럿이어도 합친다
  - 지운 것으로 적어 둔 대화도 센다. 시작한 적이 없는 것은 빠진다
  - asset 서버의 서명(ASSET_SECRET)이 아니면 401 이다. 비밀이 비어 있으면 받지 않는다
"""

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from httpx import AsyncClient, Response
from server_core.service_auth.signing import SIGNATURE_HEADER, sign
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, ImportedCharacter
from app.core.config import Settings
from app.main import API_PREFIX
from tests.conftest import TEST_AUTH_SECRET, make_test_settings

pytestmark = pytest.mark.usefixtures('clean_tables')

ASSET_SECRET = 'test-asset-secret-0123456789abcdef'
STARTS_PATH = f'{API_PREFIX}/service/stats/character-starts'
ALICE = uuid.UUID('11111111-2222-4333-8444-555555555555')
BOB = uuid.UUID('99999999-2222-4333-8444-555555555555')


@pytest.fixture
def settings() -> Settings:
    """asset 서버의 서명을 받는 설정. 주소는 비워 둔다(부르지 않는다)."""
    return make_test_settings(asset_secret=ASSET_SECRET)


async def fetch(client: AsyncClient, secret: str = ASSET_SECRET, signed_as: str | None = None) -> Response:
    """asset 서버처럼 서명해 부른다. signed_as 를 주면 그 주소로 서명한다(가로챈 서명)."""
    signature = sign(secret, int(time.time()), 'GET', signed_as or STARTS_PATH, b'')
    return await client.get(STARTS_PATH, headers={SIGNATURE_HEADER: signature})


def copy(owner: uuid.UUID, source: uuid.UUID, version: int = 1) -> ImportedCharacter:
    return ImportedCharacter(owner_id=owner, source_id=source, version=version, name='작품', rating='all', document={})


def start(owner: uuid.UUID, copied: ImportedCharacter, days_ago: int = 0, deleted: bool = False) -> Conversation:
    created = datetime.now(UTC) - timedelta(days=days_ago)
    return Conversation(
        owner_id=owner,
        character_id=copied.id,
        title='대화',
        start_title='도서관',
        start_situation='비가 온다.',
        created_at=created,
        deleted_at=created if deleted else None,
    )


async def test_counts_starts_by_the_source_work(client: AsyncClient, session: AsyncSession):
    popular, quiet, unused = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    first, second, theirs, other = copy(ALICE, popular), copy(ALICE, popular, 2), copy(BOB, popular), copy(BOB, quiet)
    session.add_all([first, second, theirs, other, copy(ALICE, unused)])
    await session.flush()
    session.add_all(
        [
            start(ALICE, first),
            start(ALICE, second, days_ago=2, deleted=True),
            start(BOB, theirs, days_ago=30),
            start(BOB, other, days_ago=8),
        ]
    )
    await session.commit()

    response = await fetch(client)

    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body['recent_days'] == 7
    assert sorted((item['work_id'], item['total'], item['recent']) for item in body['items']) == sorted(
        [(str(popular), 3, 2), (str(quiet), 1, 0)]
    )


async def test_nothing_started_is_an_empty_list(client: AsyncClient):
    response = await fetch(client)

    assert response.json() == {'recent_days': 7, 'items': []}


async def test_only_the_asset_server_signature(client: AsyncClient):
    unsigned = await client.get(STARTS_PATH)
    wrong = await fetch(client, secret=TEST_AUTH_SECRET)
    elsewhere = await fetch(client, signed_as=f'{API_PREFIX}/service/stats/other')

    assert unsigned.status_code == wrong.status_code == elsewhere.status_code == status.HTTP_401_UNAUTHORIZED


async def test_an_empty_secret_takes_nothing(client: AsyncClient, settings: Settings):
    settings.asset_secret = settings.asset_secret.__class__('')

    response = await fetch(client, secret='')

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
