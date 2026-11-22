# trpg-server/tests/test_references_wikipedia.py

"""
위키백과를 참고 자료로 넣는 틀(README 의 "위키백과")을 검증한다.

보는 것.
  - 자료와 종류: 위키백과의 줄(topic)이 DB 에 들어간다(CHECK 제약).
  - 복사하지 않는다: 찾기에 나오지 않고, 로어북·도감으로 복사하면 422 not_copyable 이며 하나도 넣지 않는다.
  - 프롬프트: [상식] 으로 보이고, 그 줄이 있을 때만 실제 세계를 쓰지 않는다는 말이 붙는다.
  - 출처 표시: 자료마다 하나다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.bestiaries.models import Monster
from app.assets.models import LoreEntry
from app.main import API_PREFIX
from app.references import service, wiki
from app.references.copying import NotCopyableError, check_copyable
from app.references.loading import load_document
from app.references.records import (
    COPYABLE_SOURCES,
    ReferenceDocument,
    ReferenceKind,
    ReferenceOrigin,
    ReferenceRecord,
    ReferenceSource,
    StoredReference,
)
from app.rounds import prompt
from app.rounds.narrator import ReferenceNote

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
REFERENCES_URL = f'{API_PREFIX}/references'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
BESTIARIES_URL = f'{API_PREFIX}/bestiaries'

CARRACK = ReferenceRecord(
    key='ko/캐럭',
    kind=ReferenceKind.TOPIC,
    name='캐럭',
    aliases=['캐럭', '카라크'],
    content='캐럭은 돛대가 서너 개인 큰 범선이다. 높은 선미루와 선수루가 있다.',
    data={'lang': 'ko', 'page_id': 1, 'revision_id': 2, 'url': 'https://ko.wikipedia.org/wiki/캐럭'},
)
TORCH = ReferenceRecord(
    key='equipment/torch',
    kind=ReferenceKind.ITEM,
    name='Torch',
    aliases=['횃불'],
    content='A torch burns.',
    name_ko='횃불',
    content_ko='횃불은 한 시간 동안 탄다.',
)
WOLF = ReferenceRecord(
    key='monsters/wolf', kind=ReferenceKind.MONSTER, name='Wolf', aliases=['늑대'], content='Medium beast.'
)


def stored(source: str, key: str = 'k') -> StoredReference:
    return StoredReference(id=uuid.uuid4(), source=source, key=key, name='이름')


def document(source: ReferenceSource, *records: ReferenceRecord) -> ReferenceDocument:
    origin = ReferenceOrigin(dataset='test', revision='abc', license='test', attribution='test')
    return ReferenceDocument(format=1, source=source, origin=origin, entries=list(records))


# --- 규칙 ---


def test_only_the_srd_can_be_copied():
    assert {ReferenceSource.SRD51} == COPYABLE_SOURCES
    check_copyable([stored('srd51')])
    with pytest.raises(NotCopyableError) as caught:
        check_copyable([stored('srd51', 'a'), stored('wikipedia', 'ko/캐럭')])

    assert caught.value.keys == ['ko/캐럭']


def test_every_source_has_an_attribution():
    assert set(service.ATTRIBUTIONS) == set(ReferenceSource)
    assert wiki.WIKIPEDIA_ATTRIBUTION in service.ATTRIBUTIONS[ReferenceSource.WIKIPEDIA]
    assert 'CC BY-SA' not in service.ATTRIBUTIONS[ReferenceSource.SRD51]


def test_a_topic_is_shown_as_common_knowledge_with_the_real_world_rule():
    topic = ReferenceNote(reference_id=uuid.uuid4(), name='캐럭', content='큰 범선이다.', kind='topic')
    item = ReferenceNote(reference_id=uuid.uuid4(), name='횃불', content='탄다.', kind='item')

    with_topic = prompt.reference_lines([item, topic])
    without = prompt.reference_lines([item])

    assert '- [상식] 캐럭: 큰 범선이다.' in with_topic
    assert prompt.REFERENCE_TOPIC_RULE in with_topic
    # 규칙은 머리말 뒤, 줄들 앞이다
    assert with_topic.index(prompt.REFERENCE_NOTE) < with_topic.index(prompt.REFERENCE_TOPIC_RULE)
    assert with_topic.index(prompt.REFERENCE_TOPIC_RULE) < with_topic.index('- [물건] 횃불: 탄다.')
    assert prompt.REFERENCE_TOPIC_RULE not in without


# --- DB 와 API ---


@pytest.fixture
def my_headers(signing_key: SigningKey) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(ME)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def ids(clean_tables: None, session: AsyncSession) -> dict[str, uuid.UUID]:
    """SRD 의 줄 둘과 위키백과의 줄 하나를 넣고 key 에서 id 로."""
    await load_document(session, document(ReferenceSource.SRD51, TORCH, WOLF))
    await load_document(session, document(ReferenceSource.WIKIPEDIA, CARRACK))
    rows = await session.execute(text('SELECT key, id FROM reference_entries'))
    return dict(rows.all())


async def make_asset(client: AsyncClient, headers: dict[str, str], url: str) -> str:
    response = await client.post(url, json={'title': '내 것'}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['id']


async def copy(client: AsyncClient, headers: dict[str, str], url: str, *reference_ids: uuid.UUID):
    return await client.post(url, json={'reference_ids': [str(item) for item in reference_ids]}, headers=headers)


async def count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


@pytest.mark.usefixtures('clean_tables')
async def test_a_wikipedia_topic_is_stored(session: AsyncSession, ids: dict[str, uuid.UUID]):
    row = (await session.execute(text("SELECT source, kind FROM reference_entries WHERE key = 'ko/캐럭'"))).one()

    assert tuple(row) == ('wikipedia', 'topic')


@pytest.mark.usefixtures('clean_tables', 'ids')
@pytest.mark.parametrize('query', [{}, {'q': '캐럭'}, {'kind': 'topic'}])
async def test_wikipedia_is_not_found_for_copying(client: AsyncClient, my_headers: dict, query: dict):
    response = await client.get(REFERENCES_URL, params=query, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert all(item['source'] == 'srd51' for item in body['items'])
    assert '캐럭' not in [item['name'] for item in body['items']]
    assert not any('CC BY-SA' in attribution for attribution in body['attributions'])


@pytest.mark.usefixtures('clean_tables')
async def test_wikipedia_is_not_copied_into_a_lorebook(
    client: AsyncClient, my_headers: dict, ids: dict[str, uuid.UUID], session: AsyncSession
):
    lorebook = await make_asset(client, my_headers, LOREBOOKS_URL)

    response = await copy(
        client, my_headers, f'{LOREBOOKS_URL}/{lorebook}/entries/copies', ids['equipment/torch'], ids['ko/캐럭']
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text
    assert response.json()['code'] == 'not_copyable'
    assert response.json()['keys'] == ['ko/캐럭']
    # 함께 고른 SRD 의 줄도 넣지 않는다
    assert await count(session, LoreEntry) == 0


@pytest.mark.usefixtures('clean_tables')
async def test_wikipedia_is_not_copied_into_a_bestiary(
    client: AsyncClient, my_headers: dict, ids: dict[str, uuid.UUID], session: AsyncSession
):
    bestiary = await make_asset(client, my_headers, BESTIARIES_URL)

    response = await copy(
        client, my_headers, f'{BESTIARIES_URL}/{bestiary}/monsters/copies', ids['monsters/wolf'], ids['ko/캐럭']
    )

    # 몬스터가 아니라는 것보다 복사할 수 없다는 것이 먼저다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text
    assert response.json()['code'] == 'not_copyable'
    assert await count(session, Monster) == 0
