# trpg-server/tests/test_references_copy.py

"""
참고 자료를 찾고 내 로어북과 도감으로 복사하는 것(#482 4단계)을 검증한다.

보는 것.
  - 옮기는 규칙(app/references/copying.py): 문장의 끝에서 자르기, 키워드, 생물 분류에서 타입으로, 종류.
  - 찾기 API: 한국어 이름, 원본의 이름, 다른 이름으로 찾는다. 종류로 거르고 쪽을 나눈다. 출처 표시가 온다.
  - 복사 API: 항목과 몬스터가 생기고 출처가 남는다. 이미 복사한 줄은 건너뛴다.
    없는 줄, 몬스터가 아닌 줄, 남의 것, 넘치는 수는 하나도 넣지 않는다.
  - DB: 출처는 자료와 key 가 함께 있거나 함께 없다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.bestiaries.models import MonsterKind
from app.assets.copies import Copy, split_copied
from app.assets.models import LOREBOOK_MAX_ENTRIES, LoreEntry, LoreKind
from app.main import API_PREFIX
from app.references import srd
from app.references.copying import (
    NotAMonsterError,
    check_monsters,
    cut_text,
    entry_copy,
    lore_keywords,
    monster_copy,
    monster_kind,
)
from app.references.loading import load_document
from app.references.records import (
    ReferenceDocument,
    ReferenceKind,
    ReferenceOrigin,
    ReferenceRecord,
    ReferenceSource,
    StoredReference,
)
from app.references.schemas import COPY_MAX_REFERENCES, ReferenceCopy
from tests.signing import SigningKey, make_access_claims, make_token

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
REFERENCES_URL = f'{API_PREFIX}/references'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
BESTIARIES_URL = f'{API_PREFIX}/bestiaries'

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
    key='monsters/wolf',
    kind=ReferenceKind.MONSTER,
    name='Wolf',
    aliases=['늑대', '이리'],
    content='Medium beast.',
    data={'type': 'beast', 'hit_points': 11},
    name_ko='늑대',
    content_ko='중형 야수. 무리로 사냥한다.',
)
LICH = ReferenceRecord(
    key='monsters/lich',
    kind=ReferenceKind.MONSTER,
    name='Lich',
    # 한국어 이름이 다른 이름에 없는 줄. 한국어 이름으로도 찾는다
    aliases=[],
    content='Medium undead.',
    data={'type': 'undead'},
    name_ko='리치',
    content_ko='중형 언데드. 성구함에 영혼을 숨긴다.',
)
# 번역이 없는 줄. 원본의 이름과 글이 보인다
ROPE = ReferenceRecord(key='equipment/rope-50', kind=ReferenceKind.ITEM, name='Rope, 50% silk', content='Rope.')


def stored(**values) -> StoredReference:
    defaults = {'id': uuid.uuid4(), 'key': 'monsters/wolf', 'name': 'Wolf', 'source': 'srd51'}
    return StoredReference(**{**defaults, **values})


# --- 옮기는 규칙 ---


def test_a_short_text_is_kept():
    assert cut_text('짧다.', 10) == '짧다.'


def test_a_long_text_is_cut_at_the_last_sentence_end():
    assert cut_text('첫 문장이다. 둘째 문장이다. 셋째 문장이다.', 17) == '첫 문장이다. 둘째 문장이다.'
    # 특성의 구분(쌍반점)에서 잘리면 마침표로 맺는다
    assert cut_text('특성: 예리한 후각; 무리 전술; 물기.', 18) == '특성: 예리한 후각; 무리 전술.'
    # 숫자 속의 점은 문장의 끝이 아니다
    assert cut_text('무게는 1.5파운드다. 그리고 더 있다.', 12) == '무게는 1.5파운드다.'
    assert cut_text('무게는 1.5파운드이고 더 있다. 끝.', 10) == '무게는 1.5파운…'


def test_a_text_without_a_sentence_end_is_cut_by_letters():
    cut = cut_text('가' * 30, 10)

    assert cut == '가' * 9 + '…'
    assert len(cut) == 10


def test_keywords_skip_one_letter_names_and_repeats():
    reference = stored(aliases=['쥐', '쥐 떼', 'Rats', 'rats', '쥐떼', '들쥐', '큰 쥐', '시궁쥐'])

    assert lore_keywords(reference) == ['쥐 떼', 'Rats', '쥐떼', '들쥐', '큰 쥐']


@pytest.mark.parametrize(
    ('kind', 'expected'),
    [
        ('humanoid', MonsterKind.HUMANOID),
        ('beast', MonsterKind.BEAST),
        ('swarm of Tiny beasts', MonsterKind.BEAST),
        ('undead', MonsterKind.UNDEAD),
        ('construct', MonsterKind.CONSTRUCT),
        ('dragon', MonsterKind.OTHER),
        (None, MonsterKind.OTHER),
    ],
)
def test_the_creature_type_becomes_a_monster_kind(kind: str | None, expected: MonsterKind):
    data = {} if kind is None else {'type': kind}

    assert monster_kind(stored(data=data)) == expected


def test_an_item_becomes_an_item_entry_and_a_monster_a_species_entry():
    item = entry_copy(stored(key='equipment/torch', name='Torch', kind='item', name_ko='횃불', content_ko='탄다.'))
    wolf = entry_copy(stored(aliases=['늑대'], kind='monster', content='Medium beast.'))

    assert (item.data.name, item.data.content, item.data.kind) == ('횃불', '탄다.', LoreKind.ITEM)
    assert (item.source, item.key) == ('srd51', 'equipment/torch')
    assert (wolf.data.name, wolf.data.content, wolf.data.kind, wolf.data.keywords) == (
        'Wolf',
        'Medium beast.',
        LoreKind.SPECIES,
        ['늑대'],
    )


def test_a_monster_copy_keeps_the_name_within_the_limit_and_cuts_the_text():
    reference = stored(kind='monster', name='A' * 80, content_ko='가' * 400 + '. ' + '나' * 200 + '.')

    copied = monster_copy(reference)

    assert copied.data.name == 'A' * 50
    assert copied.data.content == '가' * 400 + '.'
    assert copied.data.unique is False


def test_only_monsters_go_into_a_bestiary():
    check_monsters([stored(kind='monster')])
    with pytest.raises(NotAMonsterError) as caught:
        check_monsters([stored(kind='monster'), stored(key='equipment/torch', kind='item')])

    assert caught.value.keys == ['equipment/torch']


def test_copies_already_made_are_split_off_in_order():
    first, second, third = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    copies = [Copy(first, 'srd51', 'a', None), Copy(second, 'srd51', 'b', None), Copy(third, 'srd51', 'c', None)]

    fresh, skipped = split_copied(copies, {('srd51', 'b'), ('other', 'a')})

    assert [copy.reference_id for copy in fresh] == [first, third]
    assert skipped == [second]


def test_a_copy_request_takes_each_id_once_and_not_too_many():
    one, two = uuid.uuid4(), uuid.uuid4()

    assert ReferenceCopy(reference_ids=[one, two, one]).reference_ids == [one, two]
    with pytest.raises(ValidationError):
        ReferenceCopy(reference_ids=[])
    with pytest.raises(ValidationError):
        ReferenceCopy(reference_ids=[uuid.uuid4() for _ in range(COPY_MAX_REFERENCES + 1)])


# --- API ---


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def my_headers(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def their_headers(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, SOMEONE_ELSE)


def document(*records: ReferenceRecord) -> ReferenceDocument:
    origin = ReferenceOrigin(dataset='test', revision='abc', license='CC-BY-4.0', attribution='SRD 5.1')
    return ReferenceDocument(format=1, source=ReferenceSource.SRD51, origin=origin, entries=list(records))


@pytest.fixture
async def ids(clean_tables: None, session: AsyncSession) -> dict[str, uuid.UUID]:
    """테이블을 비운 뒤 참고 자료 넷을 넣고 key 에서 id 로."""
    await load_document(session, document(TORCH, WOLF, LICH, ROPE))
    rows = await session.execute(text('SELECT key, id FROM reference_entries'))
    return dict(rows.all())


async def make_asset(client: AsyncClient, headers: dict[str, str], url: str) -> str:
    response = await client.post(url, json={'title': '내 것'}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['id']


async def copy(client: AsyncClient, headers: dict[str, str], url: str, *reference_ids: uuid.UUID):
    return await client.post(url, json={'reference_ids': [str(item) for item in reference_ids]}, headers=headers)


def lore_copies_url(lorebook_id: str) -> str:
    return f'{LOREBOOKS_URL}/{lorebook_id}/entries/copies'


def monster_copies_url(bestiary_id: str) -> str:
    return f'{BESTIARIES_URL}/{bestiary_id}/monsters/copies'


async def count_entries(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(LoreEntry)) or 0


@pytest.mark.usefixtures('clean_tables')
async def test_searching_needs_login(client: AsyncClient):
    response = await client.get(REFERENCES_URL)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.usefixtures('clean_tables', 'ids')
@pytest.mark.parametrize(
    ('query', 'names'),
    [
        ({'q': '늑대'}, ['늑대']),
        ({'q': 'wol'}, ['늑대']),
        ({'q': '이리'}, ['늑대']),
        ({'q': '  리치 '}, ['리치']),
        ({'kind': 'item'}, ['Rope, 50% silk', '횃불']),
        ({'q': '%'}, ['Rope, 50% silk']),
        ({'q': '_'}, []),
        ({}, ['Rope, 50% silk', '늑대', '리치', '횃불']),
    ],
)
async def test_references_are_found_by_name_and_kind(client: AsyncClient, my_headers: dict, query: dict, names: list):
    response = await client.get(REFERENCES_URL, params=query, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert [item['name'] for item in body['items']] == names
    assert body['total'] == len(names)


@pytest.mark.usefixtures('clean_tables', 'ids')
async def test_a_page_carries_the_shown_text_and_the_attribution(client: AsyncClient, my_headers: dict):
    response = await client.get(REFERENCES_URL, params={'limit': 1, 'offset': 1}, headers=my_headers)
    empty = await client.get(REFERENCES_URL, params={'q': '없는 것'}, headers=my_headers)

    body = response.json()
    assert body['total'] == 4
    (wolf,) = body['items']
    assert wolf['name'] == '늑대' and wolf['original_name'] == 'Wolf' and wolf['content'] == WOLF.content_ko
    assert wolf['kind'] == 'monster' and wolf['source'] == 'srd51' and 'data' not in wolf
    assert body['attributions'] == [f'{srd.SRD51_ATTRIBUTION} {srd.SRD51_CHANGES}{srd.SRD51_TRANSLATED}']
    assert empty.json() == {'items': [], 'total': 0, 'attributions': []}


@pytest.mark.usefixtures('clean_tables')
async def test_references_are_copied_into_my_lorebook(client: AsyncClient, my_headers: dict, ids: dict[str, uuid.UUID]):
    lorebook = await make_asset(client, my_headers, LOREBOOKS_URL)

    response = await copy(client, my_headers, lore_copies_url(lorebook), ids['monsters/wolf'], ids['equipment/torch'])
    listed = await client.get(f'{LOREBOOKS_URL}/{lorebook}/entries', headers=my_headers)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    created = {entry['name']: entry for entry in response.json()['created']}
    # 고른 차례대로다
    assert list(created) == ['늑대', '횃불']
    assert response.json()['skipped'] == []
    assert created['횃불']['kind'] == 'item' and created['횃불']['content'] == TORCH.content_ko
    assert created['늑대']['kind'] == 'species' and created['늑대']['keywords'] == ['늑대', '이리']
    assert created['늑대']['copied_from'] == {'source': 'srd51', 'key': 'monsters/wolf'}
    assert {entry['copied_from']['key'] for entry in listed.json()} == {'equipment/torch', 'monsters/wolf'}


@pytest.mark.usefixtures('clean_tables')
async def test_a_reference_already_copied_is_skipped(
    client: AsyncClient, my_headers: dict, ids: dict[str, uuid.UUID], session: AsyncSession
):
    lorebook = await make_asset(client, my_headers, LOREBOOKS_URL)
    await copy(client, my_headers, lore_copies_url(lorebook), ids['equipment/torch'])

    again = await copy(client, my_headers, lore_copies_url(lorebook), ids['equipment/torch'], ids['monsters/lich'])

    assert again.status_code == status.HTTP_201_CREATED
    assert [entry['name'] for entry in again.json()['created']] == ['리치']
    assert again.json()['skipped'] == [str(ids['equipment/torch'])]
    assert await count_entries(session) == 2


@pytest.mark.usefixtures('clean_tables')
async def test_a_written_entry_has_no_source(client: AsyncClient, my_headers: dict):
    lorebook = await make_asset(client, my_headers, LOREBOOKS_URL)

    response = await client.post(f'{LOREBOOKS_URL}/{lorebook}/entries', json={'name': '횃불'}, headers=my_headers)

    assert response.json()['copied_from'] is None


@pytest.mark.usefixtures('clean_tables')
async def test_an_unknown_reference_copies_nothing(
    client: AsyncClient, my_headers: dict, ids: dict[str, uuid.UUID], session: AsyncSession
):
    lorebook = await make_asset(client, my_headers, LOREBOOKS_URL)
    unknown = uuid.uuid4()

    response = await copy(client, my_headers, lore_copies_url(lorebook), ids['equipment/torch'], unknown)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()['code'] == 'reference_not_found'
    assert response.json()['reference_ids'] == [str(unknown)]
    assert await count_entries(session) == 0


@pytest.mark.usefixtures('clean_tables')
async def test_someone_elses_lorebook_looks_like_it_does_not_exist(
    client: AsyncClient, my_headers: dict, their_headers: dict, ids: dict[str, uuid.UUID], session: AsyncSession
):
    lorebook = await make_asset(client, their_headers, LOREBOOKS_URL)

    response = await copy(client, my_headers, lore_copies_url(lorebook), ids['equipment/torch'])

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert await count_entries(session) == 0


@pytest.mark.usefixtures('clean_tables')
async def test_copies_that_would_overflow_the_lorebook_copy_nothing(
    client: AsyncClient, my_headers: dict, ids: dict[str, uuid.UUID], session: AsyncSession
):
    lorebook = await make_asset(client, my_headers, LOREBOOKS_URL)
    for number in range(LOREBOOK_MAX_ENTRIES - 1):
        session.add(LoreEntry(lorebook_id=uuid.UUID(lorebook), name=f'항목 {number}'))
    await session.commit()

    full = await copy(client, my_headers, lore_copies_url(lorebook), ids['equipment/torch'], ids['monsters/wolf'])
    fits = await copy(client, my_headers, lore_copies_url(lorebook), ids['equipment/torch'])

    assert full.status_code == status.HTTP_409_CONFLICT
    assert fits.status_code == status.HTTP_201_CREATED
    assert await count_entries(session) == LOREBOOK_MAX_ENTRIES


@pytest.mark.usefixtures('clean_tables')
async def test_monsters_are_copied_into_my_bestiary_with_their_kind(
    client: AsyncClient, my_headers: dict, ids: dict[str, uuid.UUID]
):
    bestiary = await make_asset(client, my_headers, BESTIARIES_URL)

    response = await copy(client, my_headers, monster_copies_url(bestiary), ids['monsters/wolf'], ids['monsters/lich'])
    again = await copy(client, my_headers, monster_copies_url(bestiary), ids['monsters/lich'])

    assert response.status_code == status.HTTP_201_CREATED, response.text
    created = {monster['name']: monster for monster in response.json()['created']}
    assert (created['늑대']['kind'], created['리치']['kind']) == ('beast', 'undead')
    assert created['리치']['content'] == LICH.content_ko and created['리치']['unique'] is False
    assert created['리치']['copied_from'] == {'source': 'srd51', 'key': 'monsters/lich'}
    assert again.json() == {'created': [], 'skipped': [str(ids['monsters/lich'])]}


@pytest.mark.usefixtures('clean_tables')
async def test_an_item_is_not_copied_into_a_bestiary(
    client: AsyncClient, my_headers: dict, ids: dict[str, uuid.UUID], session: AsyncSession
):
    bestiary = await make_asset(client, my_headers, BESTIARIES_URL)

    response = await copy(
        client, my_headers, monster_copies_url(bestiary), ids['monsters/wolf'], ids['equipment/torch']
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['code'] == 'not_a_monster' and response.json()['keys'] == ['equipment/torch']
    assert await session.scalar(text('SELECT count(*) FROM monsters')) == 0


@pytest.mark.usefixtures('clean_tables')
async def test_a_source_needs_its_key(client: AsyncClient, my_headers: dict, session: AsyncSession):
    lorebook = await make_asset(client, my_headers, LOREBOOKS_URL)
    session.add(LoreEntry(lorebook_id=uuid.UUID(lorebook), name='반쪽', copied_source='srd51'))

    with pytest.raises(IntegrityError):
        await session.commit()
