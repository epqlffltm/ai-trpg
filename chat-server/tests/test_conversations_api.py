# chat-server/tests/test_conversations_api.py

"""
대화 API(app/conversations/)를 검증한다. 실제 DB(chat_test)에서 돌고, asset 서버는 가짜다(tests/assets.py).

보는 것.
  - 시작: 캐릭터의 마지막 판과 시작 상황을 고정하고, 인사말이 첫 말이 된다. 사용자의 토큰을 asset 서버에 넘긴다.
    판의 사본은 사람마다, 판마다 하나다. 판에 없는 시작 상황은 422 이고 아무것도 저장하지 않는다
  - asset 서버의 답: 없음 404(character_not_found), 성인 확인 403, 닿지 못함 503(Retry-After). 아무것도 저장하지 않는다
  - 페르소나: 고르면 그것(없으면 404), null 이면 없이, 보내지 않으면 지난번 대화의 것(지워졌으면 없이)
  - 목록: 내 것만, 지우지 않은 것만, 볼 수 있는 등급만, 최근 것부터. 캐릭터로 거른다. 쪽을 나눈다
  - 읽기와 지우기: 남의 것, 지운 것, 볼 수 없는 등급은 404 다
  - 가지: 지금 가지의 끝에서 첫 말까지 거슬러 올라간 말들을 첫 말부터 준다
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.auth.tokens import AccessClaims
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations import repository, service
from app.conversations.models import Conversation, ConversationPersona, ImportedCharacter, Message, Role
from app.conversations.schemas import ConversationCreate
from app.core.dependencies import Viewer
from app.main import API_PREFIX
from app.ratings import Rating
from tests.assets import FakeAsset, make_character, make_persona

pytestmark = pytest.mark.usefixtures('clean_tables')

CONVERSATIONS_URL = f'{API_PREFIX}/conversations'
ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'


def bearer(signing_key: SigningKey, user_id: uuid.UUID = ME, adult: bool = False) -> dict[str, str]:
    claims = make_access_claims(sub=str(user_id))
    if adult:
        claims['adult_content'] = True
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


def token_of(headers: dict[str, str]) -> str:
    return headers['Authorization'].removeprefix('Bearer ')


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def my_adult(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, adult=True)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, SOMEONE_ELSE)


async def start(client: AsyncClient, headers: dict, **body) -> dict:
    response = await client.post(CONVERSATIONS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model))


async def listed(client: AsyncClient, headers: dict, **params) -> dict:
    response = await client.get(CONVERSATIONS_URL, params=params, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


# --- 로그인 ---


@pytest.mark.parametrize(
    ('method', 'path'), [('POST', ''), ('GET', ''), ('GET', f'/{NO_SUCH_ID}'), ('DELETE', f'/{NO_SUCH_ID}')]
)
async def test_every_address_needs_login(client: AsyncClient, method: str, path: str):
    response = await client.request(method, f'{CONVERSATIONS_URL}{path}', json={})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 시작 ---


async def test_starting_fixes_the_version_and_the_greeting(client: AsyncClient, asset: FakeAsset, mine: dict):
    character = asset.add_character(make_character(version=3))

    made = await start(client, mine, character_id=str(character.id))

    assert made['title'] == '세라'
    assert made['start'] == {'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.'}
    assert (made['character']['id'], made['character']['version']) == (str(character.id), 3)
    assert made['character']['document'] == character.document.model_dump(mode='json')
    assert made['persona'] is None
    (opening,) = made['messages']
    assert (opening['role'], opening['content'], opening['status']) == (
        'assistant',
        '어서 와요. 찾는 책이 있나요?',
        'complete',
    )
    assert opening['parent_id'] is None


async def test_the_users_token_goes_to_the_asset_server(client: AsyncClient, asset: FakeAsset, mine: dict):
    character = asset.add_character(make_character())

    await start(client, mine, character_id=str(character.id))

    assert asset.calls == [('character', character.id, token_of(mine))]


async def test_another_start_can_be_chosen(client: AsyncClient, asset: FakeAsset, mine: dict):
    character = asset.add_character(make_character())

    made = await start(client, mine, character_id=str(character.id), start=1)

    assert made['start']['title'] == '도서관'


async def test_a_start_not_in_the_version_is_422(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict
):
    character = asset.add_character(make_character())

    response = await client.post(CONVERSATIONS_URL, json={'character_id': str(character.id), 'start': 2}, headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['code'] == 'start_not_found'
    assert response.json()['starts'] == 2
    assert await count(session, Conversation) == await count(session, ImportedCharacter) == 0


async def test_without_a_greeting_there_is_no_first_message(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict
):
    character = asset.add_character(make_character(greeting='  '))

    made = await start(client, mine, character_id=str(character.id))

    assert made['messages'] == []
    assert await count(session, Message) == 0


async def test_one_copy_per_version_per_person(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict, theirs: dict
):
    character = asset.add_character(make_character())
    await start(client, mine, character_id=str(character.id))
    await start(client, mine, character_id=str(character.id))
    await start(client, theirs, character_id=str(character.id))
    asset.add_character(make_character(character.id, version=2))
    await start(client, mine, character_id=str(character.id))

    rows = await session.execute(select(ImportedCharacter.owner_id, ImportedCharacter.version))

    assert sorted(rows.all(), key=str) == sorted([(ME, 1), (SOMEONE_ELSE, 1), (ME, 2)], key=str)
    assert await count(session, Conversation) == 4


@pytest.mark.parametrize(
    ('setup', 'code', 'answer'),
    [
        ('missing', status.HTTP_404_NOT_FOUND, 'character_not_found'),
        ('adult', status.HTTP_403_FORBIDDEN, 'adult_content_required'),
        ('down', status.HTTP_503_SERVICE_UNAVAILABLE, 'asset_unavailable'),
    ],
)
async def test_what_the_asset_server_says_is_passed_on(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict, setup: str, code: int, answer: str
):
    character = make_character()
    if setup == 'adult':
        asset.add_character(character)
        asset.adult_required.add(character.id)
    asset.down = setup == 'down'

    response = await client.post(CONVERSATIONS_URL, json={'character_id': str(character.id)}, headers=mine)

    assert (response.status_code, response.json()['code']) == (code, answer)
    assert await count(session, Conversation) == 0


async def test_unavailable_asks_to_try_again_later(client: AsyncClient, asset: FakeAsset, mine: dict):
    asset.down = True

    response = await client.post(CONVERSATIONS_URL, json={'character_id': NO_SUCH_ID}, headers=mine)

    assert response.headers['Retry-After'] == '5'


async def test_an_adult_version_is_checked_here_too(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict, my_adult: dict
):
    # asset 서버가 잘못 내줘도 이 서버의 규칙(allowed_ratings)으로 한 번 더 거른다
    character = asset.add_character(make_character(rating=Rating.ADULT))

    refused = await client.post(CONVERSATIONS_URL, json={'character_id': str(character.id)}, headers=mine)
    allowed = await client.post(CONVERSATIONS_URL, json={'character_id': str(character.id)}, headers=my_adult)

    assert (refused.status_code, refused.json()['code']) == (status.HTTP_404_NOT_FOUND, 'character_not_found')
    assert allowed.status_code == status.HTTP_201_CREATED


async def test_unknown_fields_are_refused(client: AsyncClient, asset: FakeAsset, mine: dict):
    character = asset.add_character(make_character())

    response = await client.post(
        CONVERSATIONS_URL, json={'character_id': str(character.id), 'owner_id': str(SOMEONE_ELSE)}, headers=mine
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 페르소나 ---


async def test_a_chosen_persona_is_copied(client: AsyncClient, asset: FakeAsset, mine: dict):
    character = asset.add_character(make_character())
    persona = asset.add_persona(make_persona(revision=4))

    made = await start(client, mine, character_id=str(character.id), persona_id=str(persona.id))

    assert made['persona'] == {**persona.model_dump(mode='json'), 'revision': 4}
    assert asset.calls[-1] == ('persona', persona.id, token_of(mine))


async def test_a_chosen_persona_that_is_missing_is_404(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict
):
    character = asset.add_character(make_character())

    response = await client.post(
        CONVERSATIONS_URL, json={'character_id': str(character.id), 'persona_id': NO_SUCH_ID}, headers=mine
    )

    assert (response.status_code, response.json()['code']) == (status.HTTP_404_NOT_FOUND, 'persona_not_found')
    assert await count(session, Conversation) == 0


async def test_without_a_choice_the_last_persona_is_used_again(client: AsyncClient, asset: FakeAsset, mine: dict):
    character = asset.add_character(make_character())
    persona = asset.add_persona(make_persona())
    await start(client, mine, character_id=str(character.id), persona_id=str(persona.id))
    # 그사이에 고쳤다. 다시 가져오므로 새 revision 이다
    asset.add_persona(make_persona(persona.id, revision=2, name='서윤'))

    made = await start(client, mine, character_id=str(character.id))

    assert (made['persona']['id'], made['persona']['revision'], made['persona']['name']) == (str(persona.id), 2, '서윤')


async def test_null_starts_without_a_persona(client: AsyncClient, asset: FakeAsset, mine: dict):
    character = asset.add_character(make_character())
    persona = asset.add_persona(make_persona())
    await start(client, mine, character_id=str(character.id), persona_id=str(persona.id))

    made = await start(client, mine, character_id=str(character.id), persona_id=None)
    after = await start(client, mine, character_id=str(character.id))

    # null 도 고른 것이다. 그다음의 "지난번"은 페르소나 없음이다
    assert (made['persona'], after['persona']) == (None, None)


async def test_a_last_persona_deleted_since_starts_without_one(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict
):
    character = asset.add_character(make_character())
    persona = asset.add_persona(make_persona())
    await start(client, mine, character_id=str(character.id), persona_id=str(persona.id))
    del asset.personas[persona.id]

    made = await start(client, mine, character_id=str(character.id))

    assert made['persona'] is None
    assert await count(session, ConversationPersona) == 1


async def test_someone_elses_last_persona_is_not_mine(client: AsyncClient, asset: FakeAsset, mine: dict, theirs: dict):
    character = asset.add_character(make_character())
    persona = asset.add_persona(make_persona())
    await start(client, theirs, character_id=str(character.id), persona_id=str(persona.id))

    made = await start(client, mine, character_id=str(character.id))

    assert made['persona'] is None
    assert [kind for kind, _, _ in asset.calls].count('persona') == 1


async def test_reading_the_last_choices_does_not_hold_a_connection(session: AsyncSession):
    # asset 서버를 부르는 동안 DB 연결을 쥐지 않는다. 지난번 페르소나와 모델을 읽은 뒤 트랜잭션을 닫는다
    claims = AccessClaims(user_id=ME, expires_at=datetime.now(UTC) + timedelta(minutes=15))
    viewer = Viewer(claims=claims, token='t')

    await service.remember_choices(session, viewer, ConversationCreate(character_id=uuid.uuid4()))

    assert not session.in_transaction()


# --- 목록 ---


async def test_the_list_is_mine_and_newest_first(client: AsyncClient, asset: FakeAsset, mine: dict, theirs: dict):
    first = asset.add_character(make_character(name='세라'))
    second = asset.add_character(make_character(name='린'))
    older = await start(client, mine, character_id=str(first.id))
    newer = await start(client, mine, character_id=str(second.id))
    await start(client, theirs, character_id=str(first.id))

    page = await listed(client, mine)

    assert page['total'] == 2
    assert [item['id'] for item in page['items']] == [newer['id'], older['id']]
    assert page['items'][0]['character'] == {
        'id': str(second.id),
        'version': 1,
        'name': '린',
        'image_id': '0b7c6f1e-2d3a-4b5c-8d9e-0f1a2b3c4d5e',
        'rating': 'all',
    }


async def test_the_list_is_paged_and_filtered_by_character(client: AsyncClient, asset: FakeAsset, mine: dict):
    first = asset.add_character(make_character())
    second = asset.add_character(make_character())
    made = [await start(client, mine, character_id=str(first.id)) for _ in range(3)]
    await start(client, mine, character_id=str(second.id))

    page = await listed(client, mine, character_id=str(first.id), limit=2, offset=1)

    assert page['total'] == 3
    assert [item['id'] for item in page['items']] == [made[1]['id'], made[0]['id']]


async def test_deleted_and_unviewable_ones_are_not_listed(
    client: AsyncClient, asset: FakeAsset, mine: dict, my_adult: dict, signing_key: SigningKey
):
    # 운영자는 성인 확인을 하지 않았어도 성인 등급을 본다(asset 서버, 게임 서버와 같다)
    claims = make_access_claims(sub=str(ME))
    claims['roles'] = ['operator']
    operator_headers = {'Authorization': f'Bearer {make_token(signing_key, claims)}'}
    kept = asset.add_character(make_character())
    adult = asset.add_character(make_character(rating=Rating.ADULT))
    shown = await start(client, mine, character_id=str(kept.id))
    gone = await start(client, mine, character_id=str(kept.id))
    hidden = await start(client, my_adult, character_id=str(adult.id))
    await client.delete(f'{CONVERSATIONS_URL}/{gone["id"]}', headers=mine)

    plain = await listed(client, mine)
    grown = await listed(client, my_adult)

    operator = await listed(client, operator_headers)

    assert [item['id'] for item in plain['items']] == [shown['id']]
    assert {item['id'] for item in grown['items']} == {shown['id'], hidden['id']}
    assert operator['total'] == 2


# --- 읽기와 지우기 ---


async def test_reading_gives_the_same_as_starting(client: AsyncClient, asset: FakeAsset, mine: dict):
    character = asset.add_character(make_character())
    persona = asset.add_persona(make_persona())
    made = await start(client, mine, character_id=str(character.id), persona_id=str(persona.id))

    response = await client.get(f'{CONVERSATIONS_URL}/{made["id"]}', headers=mine)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == made


async def test_others_deleted_and_unviewable_are_404(
    client: AsyncClient, asset: FakeAsset, mine: dict, my_adult: dict, theirs: dict
):
    character = asset.add_character(make_character())
    adult = asset.add_character(make_character(rating=Rating.ADULT))
    made = await start(client, mine, character_id=str(character.id))
    deleted = await start(client, mine, character_id=str(character.id))
    grown = await start(client, my_adult, character_id=str(adult.id))
    await client.delete(f'{CONVERSATIONS_URL}/{deleted["id"]}', headers=mine)

    answers = [
        await client.get(f'{CONVERSATIONS_URL}/{made["id"]}', headers=theirs),
        await client.get(f'{CONVERSATIONS_URL}/{deleted["id"]}', headers=mine),
        await client.get(f'{CONVERSATIONS_URL}/{grown["id"]}', headers=mine),
        await client.get(f'{CONVERSATIONS_URL}/{NO_SUCH_ID}', headers=mine),
    ]

    assert [answer.status_code for answer in answers] == [status.HTTP_404_NOT_FOUND] * 4


async def test_deleting_marks_the_time_and_keeps_the_rows(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict, theirs: dict
):
    character = asset.add_character(make_character())
    made = await start(client, mine, character_id=str(character.id))

    refused = await client.delete(f'{CONVERSATIONS_URL}/{made["id"]}', headers=theirs)
    deleted = await client.delete(f'{CONVERSATIONS_URL}/{made["id"]}', headers=mine)
    again = await client.delete(f'{CONVERSATIONS_URL}/{made["id"]}', headers=mine)

    assert (refused.status_code, deleted.status_code, again.status_code) == (404, 204, 404)
    stored = await session.get(Conversation, uuid.UUID(made['id']))
    assert stored.deleted_at is not None
    assert await count(session, Message) == 1


# --- 가지 ---


async def test_the_path_runs_from_the_first_message_to_the_leaf(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict
):
    character = asset.add_character(make_character())
    made = await start(client, mine, character_id=str(character.id))
    conversation_id = uuid.UUID(made['id'])
    opening = uuid.UUID(made['messages'][0]['id'])
    # 한 트랜잭션에 적어 시각이 같다. 시각이 아니라 가지의 깊이로 줄 세워야 한다
    asked = Message(id=uuid.uuid4(), conversation_id=conversation_id, parent_id=opening, role=Role.USER, content='책')
    other = Message(id=uuid.uuid4(), conversation_id=conversation_id, parent_id=opening, role=Role.USER, content='차')
    answered = Message(
        id=uuid.uuid4(), conversation_id=conversation_id, parent_id=asked.id, role=Role.ASSISTANT, content='이쪽'
    )
    session.add_all([asked, other])
    await session.flush()
    session.add(answered)
    await session.commit()

    path = await repository.active_path(session, answered.id)

    assert [message.content for message in path] == ['어서 와요. 찾는 책이 있나요?', '책', '이쪽']
    assert await repository.active_path(session, None) == []
