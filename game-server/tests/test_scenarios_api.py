# game-server/tests/test_scenarios_api.py

"""
시나리오 API 를 검증한다.

모든 자산에 공통인 규칙은 세계관의 테스트가 이미 검증한다. 여기서는 시나리오만의 것을 본다.
시나리오는 다른 자산을 가리킨다. 룰북과 세계관은 하나씩, 로어북은 여러 개다. 그래서 생기는 규칙이 셋이다.
  - 자기 것이고 지우지 않은 자산만 가리킬 수 있다.
  - 가리키는 것을 바꾸거나 떼어 낼 수 있다.
  - 시나리오가 가리키는 자산은 지울 수 없다. 어느 시나리오가 쓰고 있는지 알려 준다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import (
    SCENARIO_MAX_LOREBOOKS,
    SCENARIO_OPENING_MAX_LENGTH,
    Asset,
    AssetType,
    Scenario,
    ScenarioLorebook,
    World,
)
from app.main import API_PREFIX
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
WORLDS_URL = f'{API_PREFIX}/worlds'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

# 테스트에 쓰는 예시 시나리오. 내용은 아무 뜻이 없다
TITLE = '17개 행성의 추격전'
OPENING = '사이렌이 울린다. 뒤를 돌아보니 마법소년 차림의 드워프가 망치를 들고 쫓아오고 있다.'

# 다른 자산을 가리키는 칸과, 그 칸이 가리키는 자산을 만드는 주소
REFERENCES = [('rulebook_id', RULEBOOKS_URL), ('world_id', WORLDS_URL)]


@pytest.fixture
def my_headers(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말."""
    return bearer(signing_key, ME)


@pytest.fixture
def their_headers(signing_key: SigningKey) -> dict[str, str]:
    """다른 사람의 토큰이 실린 머리말."""
    return bearer(signing_key, SOMEONE_ELSE)


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


async def create(client: AsyncClient, url: str, headers: dict[str, str], **fields) -> dict:
    """API 로 자산 하나를 만들고 응답의 본문을 돌려준다. 주소가 종류를 정한다."""
    body = {'title': TITLE}
    body.update(fields)
    response = await client.post(url, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


# --- 로그인 ---


@pytest.mark.parametrize(
    ('method', 'path'),
    [
        ('POST', ''),
        ('GET', ''),
        ('GET', '/11111111-2222-4333-8444-555555555555'),
        ('PATCH', '/11111111-2222-4333-8444-555555555555'),
        ('DELETE', '/11111111-2222-4333-8444-555555555555'),
    ],
)
async def test_every_address_requires_login(client: AsyncClient, method: str, path: str):
    response = await client.request(method, f'{SCENARIOS_URL}{path}', json={'title': '시나리오'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 만들기 ---


async def test_creates_a_draft_with_only_a_title(client: AsyncClient, my_headers: dict[str, str]):
    response = await client.post(SCENARIOS_URL, json={'title': TITLE}, headers=my_headers)

    # 임시 저장. 룰북이 없어도 만들어진다
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body['title'] == TITLE
    assert body['rulebook_id'] is None
    assert body['world_id'] is None
    assert body['lorebook_ids'] == []
    assert body['opening'] == ''


async def test_creates_a_scenario_that_points_to_my_assets(client: AsyncClient, my_headers: dict[str, str]):
    rulebook = await create(client, RULEBOOKS_URL, my_headers)
    world = await create(client, WORLDS_URL, my_headers)

    body = await create(
        client, SCENARIOS_URL, my_headers, rulebook_id=rulebook['id'], world_id=world['id'], opening=OPENING
    )

    assert body['rulebook_id'] == rulebook['id']
    assert body['world_id'] == world['id']
    assert body['opening'] == OPENING


async def test_the_response_carries_only_the_listed_fields(client: AsyncClient, my_headers: dict[str, str]):
    body = await create(client, SCENARIOS_URL, my_headers)

    assert set(body) == {
        'id',
        'title',
        'description',
        'rating',
        'visibility',
        'created_at',
        'updated_at',
        'rulebook_id',
        'world_id',
        'lorebook_ids',
        'opening',
    }


async def test_a_scenario_is_saved_as_the_scenario_type(
    client: AsyncClient, my_headers: dict[str, str], session: AsyncSession
):
    created = await create(client, SCENARIOS_URL, my_headers)

    saved_type = await session.scalar(text('SELECT type FROM assets WHERE id = :id'), {'id': created['id']})

    assert saved_type == AssetType.SCENARIO


@pytest.mark.parametrize(
    'body',
    [
        {},
        {'title': '   '},
        {'title': '시나리오', 'opening': '가' * (SCENARIO_OPENING_MAX_LENGTH + 1)},
        {'title': '시나리오', 'rulebook_id': 'not-a-uuid'},
        {'title': '시나리오', 'lorebook_ids': ['not-a-uuid']},
        {'title': '시나리오', 'lorebook_ids': NO_SUCH_ID},
        {'title': '시나리오', 'lorebook_ids': None},
        # 같은 로어북을 두 번 붙일 수 없다
        {'title': '시나리오', 'lorebook_ids': [NO_SUCH_ID, NO_SUCH_ID]},
        {
            'title': '시나리오',
            'lorebook_ids': [str(uuid.UUID(int=number)) for number in range(SCENARIO_MAX_LOREBOOKS + 1)],
        },
        # 룰북의 칸이다. 시나리오에는 없다
        {'title': '시나리오', 'gm_guide': '지침'},
        {'title': '시나리오', 'owner_id': str(SOMEONE_ELSE)},
    ],
)
async def test_rejects_bad_input(client: AsyncClient, my_headers: dict[str, str], body: dict):
    response = await client.post(SCENARIOS_URL, json=body, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 가리킬 수 있는 자산 ---


@pytest.mark.parametrize(('field', 'target_url'), REFERENCES)
async def test_rejects_an_asset_that_does_not_exist(
    client: AsyncClient, my_headers: dict[str, str], field: str, target_url: str
):
    response = await client.post(SCENARIOS_URL, json={'title': TITLE, field: NO_SUCH_ID}, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    # 어느 칸이 틀렸는지 알려 준다
    assert field in response.json()['detail']


@pytest.mark.parametrize(('field', 'target_url'), REFERENCES)
async def test_someone_elses_asset_looks_like_it_does_not_exist(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str], field: str, target_url: str
):
    theirs = await create(client, target_url, their_headers)

    stolen = await client.post(SCENARIOS_URL, json={'title': TITLE, field: theirs['id']}, headers=my_headers)
    missing = await client.post(SCENARIOS_URL, json={'title': TITLE, field: NO_SUCH_ID}, headers=my_headers)

    # 남의 자산과 없는 자산의 답이 똑같다. 그 ID 의 자산이 있다는 것이 드러나지 않는다
    assert stolen.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert stolen.json() == missing.json()


@pytest.mark.parametrize(('field', 'target_url'), REFERENCES)
async def test_rejects_a_deleted_asset(client: AsyncClient, my_headers: dict[str, str], field: str, target_url: str):
    target = await create(client, target_url, my_headers)
    await client.delete(f'{target_url}/{target["id"]}', headers=my_headers)

    response = await client.post(SCENARIOS_URL, json={'title': TITLE, field: target['id']}, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_rejects_an_asset_of_the_wrong_type(client: AsyncClient, my_headers: dict[str, str]):
    world = await create(client, WORLDS_URL, my_headers)

    # 룰북 자리에 세계관을 넣는다
    response = await client.post(SCENARIOS_URL, json={'title': TITLE, 'rulebook_id': world['id']}, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_nothing_is_saved_when_a_reference_is_rejected(client: AsyncClient, my_headers: dict[str, str]):
    rulebook = await create(client, RULEBOOKS_URL, my_headers)

    # 룰북은 맞고 세계관이 틀렸다
    body = {'title': TITLE, 'rulebook_id': rulebook['id'], 'world_id': NO_SUCH_ID}
    response = await client.post(SCENARIOS_URL, json=body, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (await client.get(SCENARIOS_URL, headers=my_headers)).json()['total'] == 0


# --- 고치기 ---


async def test_attaches_a_rulebook_later(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create(client, SCENARIOS_URL, my_headers, opening=OPENING)
    rulebook = await create(client, RULEBOOKS_URL, my_headers)

    response = await client.patch(
        f'{SCENARIOS_URL}/{scenario["id"]}', json={'rulebook_id': rulebook['id']}, headers=my_headers
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body['rulebook_id'] == rulebook['id']
    # 보내지 않은 칸은 그대로다
    assert body['opening'] == OPENING
    assert body['updated_at'] > scenario['updated_at']


@pytest.mark.parametrize(('field', 'target_url'), REFERENCES)
async def test_null_detaches_a_reference(client: AsyncClient, my_headers: dict[str, str], field: str, target_url: str):
    target = await create(client, target_url, my_headers)
    scenario = await create(client, SCENARIOS_URL, my_headers, **{field: target['id']})
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    response = await client.patch(url, json={field: None}, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()[field] is None
    assert (await client.get(url, headers=my_headers)).json()[field] is None


async def test_a_reference_that_is_not_sent_stays(client: AsyncClient, my_headers: dict[str, str]):
    rulebook = await create(client, RULEBOOKS_URL, my_headers)
    scenario = await create(client, SCENARIOS_URL, my_headers, rulebook_id=rulebook['id'])

    response = await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'opening': OPENING}, headers=my_headers)

    body = response.json()
    assert body['opening'] == OPENING
    assert body['rulebook_id'] == rulebook['id']


async def test_null_does_not_clear_other_fields(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create(client, SCENARIOS_URL, my_headers, opening=OPENING)

    # null 로 비울 수 있는 칸은 룰북과 세계관뿐이다. 나머지 칸의 null 은 "보내지 않았다"와 같다
    response = await client.patch(
        f'{SCENARIOS_URL}/{scenario["id"]}', json={'title': None, 'opening': None}, headers=my_headers
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body['title'] == TITLE
    assert body['opening'] == OPENING


async def test_a_rejected_update_changes_nothing(client: AsyncClient, my_headers: dict[str, str]):
    rulebook = await create(client, RULEBOOKS_URL, my_headers)
    scenario = await create(client, SCENARIOS_URL, my_headers, rulebook_id=rulebook['id'])
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    response = await client.patch(url, json={'title': '바꿈', 'rulebook_id': NO_SUCH_ID}, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    body = (await client.get(url, headers=my_headers)).json()
    assert body['title'] == TITLE
    assert body['rulebook_id'] == rulebook['id']


# --- 시나리오가 가리키는 자산은 지울 수 없다 ---


@pytest.mark.parametrize(('field', 'target_url'), REFERENCES)
async def test_an_asset_in_use_cannot_be_deleted(
    client: AsyncClient, my_headers: dict[str, str], field: str, target_url: str
):
    target = await create(client, target_url, my_headers)
    await create(client, SCENARIOS_URL, my_headers, **{field: target['id']})
    url = f'{target_url}/{target["id"]}'

    response = await client.delete(url, headers=my_headers)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert (await client.get(url, headers=my_headers)).status_code == status.HTTP_200_OK


@pytest.mark.parametrize(('field', 'target_url'), REFERENCES)
async def test_a_detached_asset_can_be_deleted(
    client: AsyncClient, my_headers: dict[str, str], field: str, target_url: str
):
    target = await create(client, target_url, my_headers)
    scenario = await create(client, SCENARIOS_URL, my_headers, **{field: target['id']})
    await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={field: None}, headers=my_headers)

    response = await client.delete(f'{target_url}/{target["id"]}', headers=my_headers)

    assert response.status_code == status.HTTP_204_NO_CONTENT


async def test_a_deleted_scenario_does_not_hold_its_assets(client: AsyncClient, my_headers: dict[str, str]):
    rulebook = await create(client, RULEBOOKS_URL, my_headers)
    scenario = await create(client, SCENARIOS_URL, my_headers, rulebook_id=rulebook['id'])
    await client.delete(f'{SCENARIOS_URL}/{scenario["id"]}', headers=my_headers)

    response = await client.delete(f'{RULEBOOKS_URL}/{rulebook["id"]}', headers=my_headers)

    assert response.status_code == status.HTTP_204_NO_CONTENT


async def test_deleting_a_scenario_leaves_its_assets(client: AsyncClient, my_headers: dict[str, str]):
    rulebook = await create(client, RULEBOOKS_URL, my_headers)
    scenario = await create(client, SCENARIOS_URL, my_headers, rulebook_id=rulebook['id'])
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    response = await client.delete(url, headers=my_headers)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert (await client.get(url, headers=my_headers)).status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(f'{RULEBOOKS_URL}/{rulebook["id"]}', headers=my_headers)).status_code == status.HTTP_200_OK


# --- 로어북은 여러 개 붙인다 ---


async def create_lorebooks(client: AsyncClient, headers: dict[str, str], count: int) -> list[str]:
    """로어북을 여러 개 만들고 ID 를 정렬해서 돌려준다. 응답의 목록도 ID 순서다."""
    lorebooks = [await create(client, LOREBOOKS_URL, headers, title=f'로어북 {number}') for number in range(count)]
    return sorted(lorebook['id'] for lorebook in lorebooks)


async def test_creates_a_scenario_with_lorebooks(client: AsyncClient, my_headers: dict[str, str]):
    lorebook_ids = await create_lorebooks(client, my_headers, 3)

    scenario = await create(client, SCENARIOS_URL, my_headers, lorebook_ids=lorebook_ids)

    assert scenario['lorebook_ids'] == lorebook_ids
    read = await client.get(f'{SCENARIOS_URL}/{scenario["id"]}', headers=my_headers)
    assert read.json()['lorebook_ids'] == lorebook_ids


async def test_accepts_the_most_lorebooks_allowed(client: AsyncClient, my_headers: dict[str, str]):
    lorebook_ids = await create_lorebooks(client, my_headers, SCENARIO_MAX_LOREBOOKS)

    scenario = await create(client, SCENARIOS_URL, my_headers, lorebook_ids=lorebook_ids)

    assert scenario['lorebook_ids'] == lorebook_ids


async def test_the_list_of_lorebooks_is_replaced_as_a_whole(client: AsyncClient, my_headers: dict[str, str]):
    first, second, third = await create_lorebooks(client, my_headers, 3)
    scenario = await create(client, SCENARIOS_URL, my_headers, lorebook_ids=[first, second])

    # 첫째는 떼고, 둘째는 그대로 두고, 셋째를 붙인다
    response = await client.patch(
        f'{SCENARIOS_URL}/{scenario["id"]}', json={'lorebook_ids': [second, third]}, headers=my_headers
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['lorebook_ids'] == [second, third]
    assert response.json()['updated_at'] > scenario['updated_at']


async def test_an_empty_list_detaches_every_lorebook(client: AsyncClient, my_headers: dict[str, str]):
    lorebook_ids = await create_lorebooks(client, my_headers, 2)
    scenario = await create(client, SCENARIOS_URL, my_headers, lorebook_ids=lorebook_ids)
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    response = await client.patch(url, json={'lorebook_ids': []}, headers=my_headers)

    assert response.json()['lorebook_ids'] == []
    assert (await client.get(url, headers=my_headers)).json()['lorebook_ids'] == []


async def test_lorebooks_that_are_not_sent_stay(client: AsyncClient, my_headers: dict[str, str]):
    lorebook_ids = await create_lorebooks(client, my_headers, 2)
    scenario = await create(client, SCENARIOS_URL, my_headers, lorebook_ids=lorebook_ids)
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    not_sent = await client.patch(url, json={'opening': OPENING}, headers=my_headers)
    sent_null = await client.patch(url, json={'lorebook_ids': None}, headers=my_headers)

    # 전부 떼는 것은 빈 목록이다. null 은 "보내지 않았다"와 같다
    assert not_sent.json()['lorebook_ids'] == lorebook_ids
    assert sent_null.json()['lorebook_ids'] == lorebook_ids


async def test_one_lorebook_can_be_attached_to_many_scenarios(client: AsyncClient, my_headers: dict[str, str]):
    lorebook_ids = await create_lorebooks(client, my_headers, 1)

    first = await create(client, SCENARIOS_URL, my_headers, lorebook_ids=lorebook_ids)
    second = await create(client, SCENARIOS_URL, my_headers, lorebook_ids=lorebook_ids)

    assert first['lorebook_ids'] == second['lorebook_ids'] == lorebook_ids


async def test_rejects_a_lorebook_that_cannot_be_attached(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    mine = await create(client, LOREBOOKS_URL, my_headers)
    theirs = await create(client, LOREBOOKS_URL, their_headers)
    deleted = await create(client, LOREBOOKS_URL, my_headers)
    await client.delete(f'{LOREBOOKS_URL}/{deleted["id"]}', headers=my_headers)
    world = await create(client, WORLDS_URL, my_headers)

    for bad_id in (NO_SUCH_ID, theirs['id'], deleted['id'], world['id']):
        # 맞는 것과 섞어 보내도, 하나가 틀리면 전부 거부한다
        body = {'title': TITLE, 'lorebook_ids': [mine['id'], bad_id]}
        response = await client.post(SCENARIOS_URL, json=body, headers=my_headers)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert 'lorebook_ids' in response.json()['detail']

    assert (await client.get(SCENARIOS_URL, headers=my_headers)).json()['total'] == 0


async def test_a_rejected_list_of_lorebooks_changes_nothing(client: AsyncClient, my_headers: dict[str, str]):
    lorebook_ids = await create_lorebooks(client, my_headers, 2)
    scenario = await create(client, SCENARIOS_URL, my_headers, lorebook_ids=lorebook_ids)
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    response = await client.patch(url, json={'lorebook_ids': [lorebook_ids[0], NO_SUCH_ID]}, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (await client.get(url, headers=my_headers)).json()['lorebook_ids'] == lorebook_ids


async def test_an_attached_lorebook_cannot_be_deleted(client: AsyncClient, my_headers: dict[str, str]):
    lorebook_ids = await create_lorebooks(client, my_headers, 1)
    scenario = await create(client, SCENARIOS_URL, my_headers, lorebook_ids=lorebook_ids)
    lorebook_url = f'{LOREBOOKS_URL}/{lorebook_ids[0]}'

    blocked = await client.delete(lorebook_url, headers=my_headers)
    await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'lorebook_ids': []}, headers=my_headers)
    allowed = await client.delete(lorebook_url, headers=my_headers)

    assert blocked.status_code == status.HTTP_409_CONFLICT
    assert allowed.status_code == status.HTTP_204_NO_CONTENT


# --- 지울 수 없을 때 어디에 쓰이는지 알려 준다 ---


@pytest.mark.parametrize(
    ('field', 'target_url'), [*REFERENCES, ('lorebook_ids', LOREBOOKS_URL)], ids=['rulebook', 'world', 'lorebook']
)
async def test_the_refusal_names_the_scenarios_that_use_the_asset(
    client: AsyncClient, my_headers: dict[str, str], field: str, target_url: str
):
    target = await create(client, target_url, my_headers)
    value = [target['id']] if field == 'lorebook_ids' else target['id']
    first = await create(client, SCENARIOS_URL, my_headers, title='첫 시나리오', **{field: value})
    second = await create(client, SCENARIOS_URL, my_headers, title='둘째 시나리오', **{field: value})
    await create(client, SCENARIOS_URL, my_headers, title='쓰지 않는 시나리오')

    response = await client.delete(f'{target_url}/{target["id"]}', headers=my_headers)

    assert response.status_code == status.HTTP_409_CONFLICT
    # 만든 순서대로, 쓰고 있는 시나리오만 실린다
    assert response.json()['used_by'] == [
        {'id': first['id'], 'title': '첫 시나리오'},
        {'id': second['id'], 'title': '둘째 시나리오'},
    ]


async def test_the_refusal_does_not_name_deleted_scenarios(client: AsyncClient, my_headers: dict[str, str]):
    rulebook = await create(client, RULEBOOKS_URL, my_headers)
    kept = await create(client, SCENARIOS_URL, my_headers, title='남은 시나리오', rulebook_id=rulebook['id'])
    removed = await create(client, SCENARIOS_URL, my_headers, title='지운 시나리오', rulebook_id=rulebook['id'])
    await client.delete(f'{SCENARIOS_URL}/{removed["id"]}', headers=my_headers)

    response = await client.delete(f'{RULEBOOKS_URL}/{rulebook["id"]}', headers=my_headers)

    assert response.json()['used_by'] == [{'id': kept['id'], 'title': '남은 시나리오'}]


# --- 공통 규칙이 시나리오에도 이어져 있다 ---


async def test_someone_elses_scenario_looks_like_it_does_not_exist(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    theirs = await create(client, SCENARIOS_URL, their_headers, opening=OPENING)
    url = f'{SCENARIOS_URL}/{theirs["id"]}'

    read = await client.get(url, headers=my_headers)
    update = await client.patch(url, json={'title': '빼앗음'}, headers=my_headers)
    delete = await client.delete(url, headers=my_headers)

    assert read.status_code == status.HTTP_404_NOT_FOUND
    assert update.status_code == status.HTTP_404_NOT_FOUND
    assert delete.status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(url, headers=their_headers)).json()['title'] == TITLE


async def test_the_list_does_not_carry_the_opening(client: AsyncClient, my_headers: dict[str, str]):
    await create(client, SCENARIOS_URL, my_headers, opening=OPENING)

    response = await client.get(SCENARIOS_URL, headers=my_headers)

    body = response.json()
    assert body['total'] == 1
    assert 'opening' not in body['items'][0]


# --- DB 의 마지막 방어선 ---


async def test_the_database_rejects_an_opening_that_is_too_long(session: AsyncSession):
    asset = Asset(owner_id=ME, type=AssetType.SCENARIO, title='시나리오')
    session.add(Scenario(asset=asset, opening='가' * (SCENARIO_OPENING_MAX_LENGTH + 1)))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_a_world_in_the_rulebook_column(session: AsyncSession):
    world = World(asset=Asset(owner_id=ME, type=AssetType.WORLD, title='세계'))
    session.add(world)
    await session.commit()

    # 서비스를 거치지 않고 룰북 자리에 세계관의 ID 를 넣는다. 외래 키가 rulebooks 를 가리키므로 DB 가 막는다
    asset = Asset(owner_id=ME, type=AssetType.SCENARIO, title='시나리오')
    session.add(Scenario(asset=asset, rulebook_id=world.asset_id))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_a_world_as_an_attached_lorebook(session: AsyncSession):
    world = World(asset=Asset(owner_id=ME, type=AssetType.WORLD, title='세계'))
    scenario = Scenario(asset=Asset(owner_id=ME, type=AssetType.SCENARIO, title='시나리오'))
    session.add_all([world, scenario])
    await session.commit()

    # 서비스를 거치지 않고 로어북 자리에 세계관의 ID 를 넣는다
    session.add(ScenarioLorebook(scenario_id=scenario.asset_id, lorebook_id=world.asset_id))

    with pytest.raises(IntegrityError):
        await session.commit()
