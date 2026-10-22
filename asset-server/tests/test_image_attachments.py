# asset-server/tests/test_image_attachments.py

"""
그림을 붙이고, 공개 캐릭터의 그림을 남이 보고, 탈퇴할 때 그림을 지우는 것을 검증한다(#566 의 둘째 조각).
그림의 행은 바로 적고(tests/images.py 의 own_image), 저장소는 가짜다.

보는 것.
  - 붙이기: 페르소나와 캐릭터의 대표 그림은 자기 그림만이다. 남의 그림, 없는 그림은 422 image_not_owned 다. 떼기는 된다
  - 게시: 소개 글에 남의 그림이 있으면 막는다(image_not_owned). 게시하면 판에 쓰인 그림(대표 + 소개)을 적는다
  - 보기: 공개 캐릭터의 판에 쓰인 그림은 그 판의 등급을 볼 수 있는 사람이 본다(로그인 없이도 전체 이용가).
    비공개, 게시 전의 초안, 지운 캐릭터, 페르소나의 그림은 주인만 본다. 옛 판의 그림도 보인다
  - 탈퇴: 어느 판에도 쓰이지 않은 그 사람의 그림을 저장소와 표에서 지운다. 남긴 공개 캐릭터의 판에 쓰인 그림은 남는다.
    초안이 가리키던 그림을 지우면 초안의 image_id 가 비워진다. 저장소가 고장이면 503 이고 다시 오면 마저 지운다
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.models import Character, CharacterVersion
from app.images.models import Image, ImageUse
from app.main import API_PREFIX
from tests.images import FakeImageStore, StoredObject, own_image
from tests.signing import signed_withdrawal

pytestmark = pytest.mark.usefixtures('clean_tables')

OWNER = uuid.UUID('11111111-2222-4333-8444-555555555555')
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')
CHARACTERS_URL = f'{API_PREFIX}/characters'
PERSONAS_URL = f'{API_PREFIX}/personas'
IMAGES_URL = f'{API_PREFIX}/images'
NOT_OWNED = {'detail': '자기가 올린 그림만 붙일 수 있습니다.', 'code': 'image_not_owned'}
START = [{'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.'}]


def bearer(signing_key: SigningKey, user_id: uuid.UUID, adult: bool = False) -> dict[str, str]:
    # 1~2단계에는 운영자만 캐릭터를 만들고 공개로 둔다. 만드는 사람은 운영자로 둔다
    claims = make_access_claims(sub=str(user_id))
    claims['roles'] = ['operator'] if user_id == OWNER else []
    if adult:
        claims['adult_content'] = True
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
def owner(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, OWNER)


@pytest.fixture
def other(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, OTHER)


@pytest.fixture
def adult(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, OTHER, adult=True)


@pytest.fixture
def store(app: FastAPI) -> FakeImageStore:
    fake = FakeImageStore()
    app.state.image_store = fake
    return fake


def intro_with(image_id: str) -> str:
    return f'<p>소개</p><img src="/api/v1/asset/images/{image_id}" alt="그림">'


async def create_character(client: AsyncClient, headers: dict, **fields) -> dict:
    response = await client.post(CHARACTERS_URL, json={'name': '세라', 'starts': START, **fields}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def publish(client: AsyncClient, headers: dict, character: dict):
    return await client.post(f'{CHARACTERS_URL}/{character["id"]}/versions', json={}, headers=headers)


async def published_public(client: AsyncClient, headers: dict, **fields) -> dict:
    """공개로 두고 게시한 캐릭터."""
    character = await create_character(client, headers, **fields)
    await client.patch(f'{CHARACTERS_URL}/{character["id"]}', json={'visibility': 'public'}, headers=headers)
    response = await publish(client, headers, character)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return character


async def sees(client: AsyncClient, image_id: str, headers: dict | None = None) -> int:
    """그 사람이 그 그림을 달라고 했을 때의 상태 코드."""
    return (await client.get(f'{IMAGES_URL}/{image_id}', headers=headers or {})).status_code


# --- 붙이기 ---


async def test_a_persona_takes_only_its_owners_image(
    client: AsyncClient, owner: dict, session: AsyncSession, store: FakeImageStore
):
    mine = await own_image(session, OWNER)
    theirs = await own_image(session, OTHER)

    made = await client.post(PERSONAS_URL, json={'name': '나', 'image_id': mine}, headers=owner)
    foreign = await client.post(PERSONAS_URL, json={'name': '나', 'image_id': theirs}, headers=owner)
    missing = await client.post(PERSONAS_URL, json={'name': '나', 'image_id': str(uuid.uuid4())}, headers=owner)
    swapped = await client.patch(f'{PERSONAS_URL}/{made.json()["id"]}', json={'image_id': theirs}, headers=owner)
    detached = await client.patch(f'{PERSONAS_URL}/{made.json()["id"]}', json={'image_id': None}, headers=owner)

    assert (made.status_code, made.json()['image_id']) == (status.HTTP_201_CREATED, mine)
    for refused in (foreign, missing, swapped):
        assert (refused.status_code, refused.json()) == (status.HTTP_422_UNPROCESSABLE_CONTENT, NOT_OWNED)
    assert (detached.status_code, detached.json()['image_id']) == (status.HTTP_200_OK, None)


async def test_a_character_takes_only_its_owners_image(
    client: AsyncClient, owner: dict, session: AsyncSession, store: FakeImageStore
):
    mine = await own_image(session, OWNER)
    theirs = await own_image(session, OTHER)

    foreign = await client.post(
        CHARACTERS_URL, json={'name': '세라', 'starts': START, 'image_id': theirs}, headers=owner
    )
    character = await create_character(client, owner)
    attached = await client.patch(f'{CHARACTERS_URL}/{character["id"]}', json={'image_id': mine}, headers=owner)
    swapped = await client.patch(f'{CHARACTERS_URL}/{character["id"]}', json={'image_id': theirs}, headers=owner)

    assert (foreign.status_code, foreign.json()) == (status.HTTP_422_UNPROCESSABLE_CONTENT, NOT_OWNED)
    assert attached.json()['image_id'] == mine
    assert (swapped.status_code, swapped.json()) == (status.HTTP_422_UNPROCESSABLE_CONTENT, NOT_OWNED)


# --- 게시 ---


async def test_a_foreign_image_in_the_intro_blocks_publishing(
    client: AsyncClient, owner: dict, session: AsyncSession, store: FakeImageStore
):
    theirs = await own_image(session, OTHER)
    character = await create_character(client, owner, intro_html=intro_with(theirs))

    check = await client.get(f'{CHARACTERS_URL}/{character["id"]}/publish-check', headers=owner)
    response = await publish(client, owner, character)

    assert check.json()['problems'] == ['image_not_owned']
    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'image_not_owned' in response.text
    assert await session.scalar(select(CharacterVersion.id)) is None


async def test_publishing_records_the_images_of_the_version(
    client: AsyncClient, owner: dict, session: AsyncSession, store: FakeImageStore
):
    cover = await own_image(session, OWNER)
    inside = await own_image(session, OWNER)
    character = await create_character(client, owner, image_id=cover, intro_html=intro_with(inside) + intro_with(cover))

    response = await publish(client, owner, character)

    uses = (await session.execute(select(ImageUse.version_id, ImageUse.image_id))).all()
    version_id = await session.scalar(select(CharacterVersion.id))
    assert response.status_code == status.HTTP_201_CREATED
    # 같은 그림이 두 번 나와도 한 줄이다
    assert sorted((str(version), str(image)) for version, image in uses) == sorted(
        [(str(version_id), cover), (str(version_id), inside)]
    )


# --- 보기 ---


async def test_a_public_characters_image_is_seen_by_anyone(
    client: AsyncClient, owner: dict, other: dict, session: AsyncSession, store: FakeImageStore
):
    cover = await own_image(session, OWNER)
    inside = await own_image(session, OWNER)
    await published_public(client, owner, image_id=cover, intro_html=intro_with(inside))

    assert [await sees(client, image_id) for image_id in (cover, inside)] == [status.HTTP_200_OK] * 2
    assert await sees(client, cover, other) == status.HTTP_200_OK


async def test_an_adult_version_shows_its_images_to_adults_only(
    client: AsyncClient, owner: dict, other: dict, adult: dict, session: AsyncSession, store: FakeImageStore
):
    cover = await own_image(session, OWNER)
    await published_public(client, owner, image_id=cover, rating='adult')

    assert (await sees(client, cover), await sees(client, cover, other)) == (status.HTTP_404_NOT_FOUND,) * 2
    assert await sees(client, cover, adult) == status.HTTP_200_OK


async def test_private_draft_and_persona_images_stay_with_the_owner(
    client: AsyncClient, owner: dict, other: dict, session: AsyncSession, store: FakeImageStore
):
    private = await own_image(session, OWNER)
    draft_only = await own_image(session, OWNER)
    persona = await own_image(session, OWNER)
    hidden = await create_character(client, owner, image_id=private)
    await publish(client, owner, hidden)
    public = await published_public(client, owner)
    await client.patch(f'{CHARACTERS_URL}/{public["id"]}', json={'image_id': draft_only}, headers=owner)
    await client.post(PERSONAS_URL, json={'name': '나', 'image_id': persona}, headers=owner)

    for image_id in (private, draft_only, persona):
        assert (await sees(client, image_id, other), await sees(client, image_id, owner)) == (
            status.HTTP_404_NOT_FOUND,
            status.HTTP_200_OK,
        )


async def test_an_old_versions_image_stays_visible(
    client: AsyncClient, owner: dict, other: dict, session: AsyncSession, store: FakeImageStore
):
    old = await own_image(session, OWNER)
    new = await own_image(session, OWNER)
    character = await published_public(client, owner, image_id=old)
    await client.patch(f'{CHARACTERS_URL}/{character["id"]}', json={'image_id': new}, headers=owner)
    await publish(client, owner, character)

    # 대화는 옛 판을 사본으로 갖고 있다. 옛 판의 대표 그림도 보여야 한다
    assert (await sees(client, old, other), await sees(client, new, other)) == (status.HTTP_200_OK,) * 2


async def test_private_again_or_deleted_hides_the_images(
    client: AsyncClient, owner: dict, other: dict, session: AsyncSession, store: FakeImageStore
):
    hidden = await own_image(session, OWNER)
    gone = await own_image(session, OWNER)
    first = await published_public(client, owner, image_id=hidden)
    second = await published_public(client, owner, image_id=gone)

    await client.patch(f'{CHARACTERS_URL}/{first["id"]}', json={'visibility': 'private'}, headers=owner)
    await client.delete(f'{CHARACTERS_URL}/{second["id"]}', headers=owner)

    assert (await sees(client, hidden, other), await sees(client, gone, other)) == (status.HTTP_404_NOT_FOUND,) * 2
    assert await sees(client, gone, owner) == status.HTTP_200_OK


# --- 탈퇴 ---


async def stored(session: AsyncSession, store: FakeImageStore, owner_id: uuid.UUID) -> str:
    """행과 저장소의 바이트가 함께 있는 그림."""
    image_id = await own_image(session, owner_id)
    store.objects[image_id] = StoredObject(b'bytes', 'image/png')
    return image_id


async def image_ids(session: AsyncSession) -> set[str]:
    session.expire_all()
    return {str(image_id) for image_id in await session.scalars(select(Image.id))}


async def test_withdrawal_erases_the_images_no_kept_version_uses(
    client: AsyncClient, owner: dict, session: AsyncSession, store: FakeImageStore
):
    kept = await stored(session, store, OWNER)
    draft = await stored(session, store, OWNER)
    persona = await stored(session, store, OWNER)
    private = await stored(session, store, OWNER)
    loose = await stored(session, store, OWNER)
    someone_elses = await stored(session, store, OTHER)
    public = await published_public(client, owner, image_id=kept)
    await client.patch(f'{CHARACTERS_URL}/{public["id"]}', json={'image_id': draft}, headers=owner)
    await client.post(PERSONAS_URL, json={'name': '나', 'image_id': persona}, headers=owner)
    hidden = await create_character(client, owner, image_id=private)
    await publish(client, owner, hidden)

    response = await signed_withdrawal(client, str(OWNER))

    assert response.status_code == status.HTTP_200_OK
    # 남긴 공개 캐릭터의 판에 쓰인 그림과 남의 그림만 남는다
    assert await image_ids(session) == {kept, someone_elses}
    assert set(store.objects) == {kept, someone_elses}
    assert not {draft, persona, private, loose} & set(store.objects)
    # 초안이 가리키던 그림이 지워져 초안의 대표 그림이 비었다
    assert (await session.get(Character, uuid.UUID(public['id']))).image_id is None


async def test_a_broken_store_fails_the_withdrawal_and_a_retry_finishes_it(
    client: AsyncClient, session: AsyncSession, store: FakeImageStore
):
    loose = await stored(session, store, OWNER)
    store.broken = True

    failed = await signed_withdrawal(client, str(OWNER))
    left = await image_ids(session)
    store.broken = False
    retried = await signed_withdrawal(client, str(OWNER))
    again = await signed_withdrawal(client, str(OWNER))

    # 인증 서버는 200 이 아니면 다시 보낸다. 행이 남아 있어 다시 온 알림이 마저 지운다
    assert failed.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert left == {loose}
    assert (retried.status_code, again.status_code) == (status.HTTP_200_OK, status.HTTP_200_OK)
    assert (await image_ids(session), store.objects) == (set(), {})
