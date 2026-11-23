# chat-server/tests/test_references_api.py

"""
참고 자료(SRD 5.1, 위키백과, #1338)를 API 로 검증한다. 실제 DB(chat_test)에서 돈다.
임베딩 모델, asset 서버, 결제 서버, 대화 모델은 가짜다. 줄은 벡터 없이 넣어 다른 이름으로만 걸리게 한다.

보는 것.
  - 대화는 꺼진 채로 시작한다. 판이 허용하면 켜고 끌 수 있다. 허용하지 않으면 켜기는 422, 끄기는 된다
  - 남의 대화는 404 다
  - 켠 대화에서 말하면 카드의 로어북 뒤, 지금 앞에 "[참고 자료]" 가 들어간다. 끄면 없다
  - 판이 허용하지 않으면 켜져 있어도(허용을 바꾼 판) 섞지 않는다
  - 임베더를 끄면(EMBEDDER=off) 켠 대화도 참고 자료 없이 돈다
  - 관리 명령이 이 서버의 표에 넣는다
"""

import asyncio
import uuid
from pathlib import Path

import pytest
from ai_core.fake import FakeEmbedder
from fastapi import FastAPI, status
from httpx import AsyncClient
from reference_core.commands import DONE
from reference_core.finder import ReferenceFinder
from reference_core.loading import load_document
from reference_core.records import (
    ReferenceDocument,
    ReferenceKind,
    ReferenceOrigin,
    ReferenceRecord,
    ReferenceSource,
    write_document,
)
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import ImportedCharacter
from app.references.models import TABLES, ReferenceEmbedding, ReferenceEntry
from app.references.setup import FIND_OPERATION, build_reference_finder
from scripts import references as script
from tests.assets import FakeAsset, make_character
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, bearer, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

GALLEON = ReferenceRecord(
    key='equipment/galleon',
    kind=ReferenceKind.ITEM,
    name='Galleon',
    aliases=['갤리온'],
    content='A ship.',
    name_ko='갤리온',
    content_ko='돛대가 셋인 큰 배다.',
)
CARRACK = ReferenceRecord(
    key='ko/캐럭', kind=ReferenceKind.TOPIC, name='캐럭', aliases=['캐럭'], content='큰 범선이다.'
)
TOWER = {
    'id': 'tower',
    'name': '붉은 탑',
    'kind': 'place',
    'keywords': [],
    'content': '별을 보는 방.',
    'constant': True,
}
BOOK = {'id': '0c1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d', 'version': 1, 'name': '세계', 'entries': [TOWER]}


def reference_document(*records: ReferenceRecord, source: ReferenceSource = ReferenceSource.SRD51) -> ReferenceDocument:
    origin = ReferenceOrigin(dataset='test', revision='abc', license='test', attribution='test')
    return ReferenceDocument(format=1, source=source, origin=origin, entries=list(records))


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter(ScriptedProvider(pieces=['그래요.']))
    app.state.model_router = fake
    return fake


@pytest.fixture
def finder(app: FastAPI) -> ReferenceFinder:
    """참고 자료 찾기를 켠다(EMBEDDER=fake 와 같다). 테스트의 설정은 임베더를 끈다."""
    made = build_reference_finder(app.state.session_factory, FakeEmbedder())
    assert made is not None
    app.state.reference_finder = made
    return made


@pytest.fixture
async def loaded(clean_tables: None, session: AsyncSession) -> None:
    """SRD 의 줄 하나와 위키백과의 줄 하나를 벡터 없이 넣는다. 다른 이름으로만 걸린다. 표를 비운 뒤에 넣는다."""
    await load_document(TABLES, session, reference_document(GALLEON))
    await load_document(TABLES, session, reference_document(CARRACK, source=ReferenceSource.WIKIPEDIA))


async def start(client: AsyncClient, session: AsyncSession, asset: FakeAsset, headers: dict, allowed: bool) -> dict:
    await turn_on_luna(session)
    character = asset.add_character(make_character(world={'lorebooks': [BOOK], 'references_allowed': allowed}))
    response = await client.post(
        CONVERSATIONS_URL, json={'character_id': str(character.id), 'model': 'luna'}, headers=headers
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def switch(client: AsyncClient, headers: dict, conversation: dict, enabled: bool):
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/references'
    return await client.put(url, json={'enabled': enabled}, headers=headers)


async def say(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, content: str) -> None:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': content}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))


def card(router: FakeRouter) -> str:
    return router.provider.calls[-1][0][0].content


# --- 켜기 ---


async def test_a_conversation_starts_without_references(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, allowed=True)

    assert conversation['references_enabled'] is False
    assert conversation['character']['document']['references_allowed'] is True


async def test_an_allowed_conversation_switches_on_and_off(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, allowed=True)

    on = await switch(client, mine, conversation, True)
    read = await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)
    off = await switch(client, mine, conversation, False)

    assert (on.status_code, on.json()) == (status.HTTP_200_OK, {'enabled': True})
    assert read.json()['references_enabled'] is True
    # 켜기를 바꿔도 목록의 차례(최근에 말한 것부터)는 그대로다
    assert read.json()['updated_at'] == conversation['updated_at']
    assert off.json() == {'enabled': False}


async def test_a_conversation_that_is_not_allowed_cannot_switch_on(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, allowed=False)

    on = await switch(client, mine, conversation, True)
    off = await switch(client, mine, conversation, False)

    assert on.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert on.json()['code'] == 'references_not_allowed'
    assert off.status_code == status.HTTP_200_OK


async def test_someone_elses_conversation_is_not_found(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict, signing_key: SigningKey
):
    conversation = await start(client, session, asset, mine, allowed=True)

    response = await switch(client, bearer(signing_key, uuid.uuid4()), conversation, True)

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_an_unknown_field_is_refused(client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict):
    conversation = await start(client, session, asset, mine, allowed=True)

    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/references'
    response = await client.put(url, json={'enabled': True, 'sources': ['srd51']}, headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 카드 ---


@pytest.mark.usefixtures('loaded', 'finder')
async def test_a_switched_on_conversation_gets_the_references_after_the_lorebook(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start(client, session, asset, mine, allowed=True)
    await switch(client, mine, conversation, True)

    await say(client, app, mine, conversation, '저 갤리온 옆의 캐럭 좀 봐')

    text = card(router)
    assert '- [물건] 갤리온: 돛대가 셋인 큰 배다.' in text
    assert '- [상식] 캐럭: 큰 범선이다.' in text
    assert '실제 세계의 나라, 도시, 인물, 연도는 장면에 쓰지 않는다.' in text
    assert text.index('[로어북]') < text.index('[참고 자료]') < text.index('[지금]')


@pytest.mark.usefixtures('loaded', 'finder')
async def test_a_switched_off_conversation_gets_none(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start(client, session, asset, mine, allowed=True)

    await say(client, app, mine, conversation, '저 갤리온 좀 봐')

    assert '[참고 자료]' not in card(router)


@pytest.mark.usefixtures('loaded', 'finder')
async def test_a_copy_that_does_not_allow_gets_none_even_when_on(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start(client, session, asset, mine, allowed=True)
    await switch(client, mine, conversation, True)
    # 사본의 허용이 꺼진 것으로 바꾼다(켠 뒤에 허용을 잃은 경우를 흉내 낸다)
    copy = await session.scalar(select(ImportedCharacter))
    assert copy is not None
    document = {**copy.document, 'references_allowed': False}
    await session.execute(update(ImportedCharacter).values(document=document))
    await session.commit()

    await say(client, app, mine, conversation, '저 갤리온 좀 봐')

    assert '[참고 자료]' not in card(router)


@pytest.mark.usefixtures('loaded')
async def test_without_the_embedder_a_switched_on_conversation_gets_none(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    assert app.state.reference_finder is None
    conversation = await start(client, session, asset, mine, allowed=True)
    await switch(client, mine, conversation, True)

    await say(client, app, mine, conversation, '저 갤리온 좀 봐')

    assert '[참고 자료]' not in card(router)


# --- 관리 명령 ---


async def test_the_commands_fill_this_servers_tables(app: FastAPI, session: AsyncSession, tmp_path: Path):
    path = tmp_path / 'refs.json'
    write_document(reference_document(GALLEON), path)

    loaded = await script.load_files(app.state.session_factory, [path])
    indexed = await script.index(app.state.session_factory, FakeEmbedder())

    assert loaded == (DONE, ['srd51: 더함 1, 고침 0(벡터를 다시 만들 것 0), 지움 0'])
    assert indexed == (DONE, ['모델 fake: 벡터 1개를 새로 만들었다'])
    assert await session.scalar(select(func.count()).select_from(ReferenceEntry)) == 1
    assert await session.scalar(select(func.count()).select_from(ReferenceEmbedding)) == 1


def test_the_finder_logs_under_this_servers_operation(app: FastAPI):
    made = build_reference_finder(app.state.session_factory, FakeEmbedder())

    assert made is not None and made.operation == FIND_OPERATION == 'chat.reference_find'
    assert build_reference_finder(app.state.session_factory, None) is None
