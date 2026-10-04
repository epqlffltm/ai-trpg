# game-server/tests/test_versions_api.py

"""
시나리오의 게시를 검증한다.

게시는 초안의 지금 내용을 판으로 굳히는 일이다. 보는 것은 넷이다.
  - 조건을 갖춘 시나리오만 게시된다. 못 갖췄으면 이유를 전부 알려 준다.
  - 판에는 시나리오와 그것이 가리키는 자산의 내용이 통째로 들어간다.
  - 판은 굳는다. 게시한 뒤에 초안을 고치거나 지워도 판은 그대로다.
  - 판은 만든 사람만 본다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import VERSION_NOTE_MAX_LENGTH, Asset, AssetType, Scenario, ScenarioVersion
from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT
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

# 테스트에 쓰는 예시. 내용은 아무 뜻이 없다
TITLE = '17개 행성의 추격전'
OPENING = '사이렌이 울린다. 뒤를 돌아보니 마법소년 차림의 드워프가 망치를 들고 쫓아오고 있다.'
GM_GUIDE = '진지한 장면은 금지다. 모든 추격은 바이크로 한다.'
SETTING = '17개 행성이 고속도로 하나로 이어져 있다.'
GM_NOTES = '고속도로의 끝에는 아무것도 없다.'


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


def versions_url(scenario: dict) -> str:
    """시나리오의 판 주소."""
    return f'{SCENARIOS_URL}/{scenario["id"]}/versions'


async def create(client: AsyncClient, url: str, headers: dict[str, str], **fields) -> dict:
    """API 로 자산 하나를 만들고 응답의 본문을 돌려준다. 주소가 종류를 정한다."""
    body = {'title': TITLE}
    body.update(fields)
    response = await client.post(url, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def create_ready_scenario(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    """게시할 조건을 갖춘 시나리오를 만든다. 룰북이 붙어 있고 도입부가 있다."""
    rulebook = await create(client, RULEBOOKS_URL, headers, title='룰북', gm_guide=GM_GUIDE)
    values = {'rulebook_id': rulebook['id'], 'opening': OPENING}
    values.update(fields)
    return await create(client, SCENARIOS_URL, headers, **values)


async def publish(client: AsyncClient, headers: dict[str, str], scenario: dict, **fields) -> dict:
    """API 로 시나리오를 게시하고 응답의 본문을 돌려준다."""
    response = await client.post(versions_url(scenario), json=fields, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


# --- 로그인 ---


@pytest.mark.parametrize(
    ('method', 'path'),
    [
        ('POST', '/11111111-2222-4333-8444-555555555555/versions'),
        ('GET', '/11111111-2222-4333-8444-555555555555/versions'),
        ('GET', '/11111111-2222-4333-8444-555555555555/versions/1'),
    ],
)
async def test_every_address_requires_login(client: AsyncClient, method: str, path: str):
    response = await client.request(method, f'{SCENARIOS_URL}{path}', json={})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 게시 ---


async def test_publishes_the_first_version(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_ready_scenario(client, my_headers)

    response = await client.post(versions_url(scenario), json={'note': '첫 판'}, headers=my_headers)

    assert response.status_code == status.HTTP_201_CREATED
    version = response.json()
    assert set(version) == {'id', 'number', 'note', 'created_at', 'snapshot'}
    assert version['number'] == 1
    assert version['note'] == '첫 판'


async def test_the_note_is_optional(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_ready_scenario(client, my_headers)

    # 본문 없이 보내도 된다
    version = await publish(client, my_headers, scenario)

    assert version['note'] == ''


async def test_numbers_go_up_by_one(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_ready_scenario(client, my_headers)

    numbers = [(await publish(client, my_headers, scenario))['number'] for _ in range(3)]

    assert numbers == [1, 2, 3]


async def test_numbers_are_counted_for_each_scenario(client: AsyncClient, my_headers: dict[str, str]):
    first = await create_ready_scenario(client, my_headers)
    second = await create_ready_scenario(client, my_headers)
    await publish(client, my_headers, first)
    await publish(client, my_headers, first)

    version = await publish(client, my_headers, second)

    assert version['number'] == 1


@pytest.mark.parametrize(
    'body',
    [
        {'note': '가' * (VERSION_NOTE_MAX_LENGTH + 1)},
        # 판의 내용과 번호는 서버가 정한다. 끼워 보내면 거부한다
        {'snapshot': {'title': '내 마음대로'}},
        {'number': 7},
    ],
)
async def test_rejects_bad_input(client: AsyncClient, my_headers: dict[str, str], body: dict):
    scenario = await create_ready_scenario(client, my_headers)

    response = await client.post(versions_url(scenario), json=body, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (await client.get(versions_url(scenario), headers=my_headers)).json() == []


# --- 게시할 조건 ---


async def test_a_scenario_without_a_rulebook_cannot_be_published(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create(client, SCENARIOS_URL, my_headers, opening=OPENING)

    response = await client.post(versions_url(scenario), json={}, headers=my_headers)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['rulebook_missing']
    assert (await client.get(versions_url(scenario), headers=my_headers)).json() == []


@pytest.mark.parametrize('opening', ['', '   \n  '])
async def test_a_scenario_without_an_opening_cannot_be_published(
    client: AsyncClient, my_headers: dict[str, str], opening: str
):
    scenario = await create_ready_scenario(client, my_headers, opening=opening)

    response = await client.post(versions_url(scenario), json={}, headers=my_headers)

    # 공백뿐인 도입부도 비어 있는 것이다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['opening_empty']


async def test_the_refusal_lists_every_problem(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create(client, SCENARIOS_URL, my_headers)

    response = await client.post(versions_url(scenario), json={}, headers=my_headers)

    # 하나씩 고치고 다시 시도하지 않게 한 번에 알려 준다
    assert response.json()['problems'] == ['rulebook_missing', 'opening_empty']


async def test_the_rating_comes_from_the_scenario_alone(client: AsyncClient, my_headers: dict[str, str]):
    adult_world = await create(client, WORLDS_URL, my_headers, rating='adult')
    all_ages = await create_ready_scenario(client, my_headers, world_id=adult_world['id'])
    adult = await create_ready_scenario(client, my_headers, rating='adult')

    # 등급은 시나리오를 조립할 때 제작자가 정한다. 재료의 등급은 게시를 막지도, 판의 등급을 바꾸지도 않는다
    assert (await publish(client, my_headers, all_ages))['snapshot']['rating'] == 'all'
    assert (await publish(client, my_headers, adult))['snapshot']['rating'] == 'adult'


async def test_fixing_the_problems_lets_it_publish(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create(client, SCENARIOS_URL, my_headers)
    rulebook = await create(client, RULEBOOKS_URL, my_headers)
    await client.patch(
        f'{SCENARIOS_URL}/{scenario["id"]}',
        json={'rulebook_id': rulebook['id'], 'opening': OPENING},
        headers=my_headers,
    )

    version = await publish(client, my_headers, scenario)

    assert version['number'] == 1


# --- 판에 들어가는 것 ---


async def test_the_snapshot_carries_everything_needed_to_play(client: AsyncClient, my_headers: dict[str, str]):
    rulebook = await create(client, RULEBOOKS_URL, my_headers, title='룰북', gm_guide=GM_GUIDE)
    world = await create(client, WORLDS_URL, my_headers, title='세계관', setting=SETTING, gm_notes=GM_NOTES)
    lorebook = await create(client, LOREBOOKS_URL, my_headers, title='인명사전')
    entries_url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    entry = (
        await client.post(
            entries_url, json={'name': '스미스', 'keywords': ['드워프'], 'content': '추격자'}, headers=my_headers
        )
    ).json()
    scenario = await create(
        client,
        SCENARIOS_URL,
        my_headers,
        description='소개글',
        rulebook_id=rulebook['id'],
        world_id=world['id'],
        lorebook_ids=[lorebook['id']],
        opening=OPENING,
    )

    version = await publish(client, my_headers, scenario)

    assert version['snapshot'] == {
        'format': SNAPSHOT_FORMAT,
        'title': TITLE,
        'description': '소개글',
        'rating': 'all',
        'opening': OPENING,
        'rulebook': {'id': rulebook['id'], 'title': '룰북', 'gm_guide': GM_GUIDE},
        'world': {'id': world['id'], 'title': '세계관', 'setting': SETTING, 'gm_notes': GM_NOTES},
        'lorebooks': [
            {
                'id': lorebook['id'],
                'title': '인명사전',
                'entries': [{'id': entry['id'], 'name': '스미스', 'keywords': ['드워프'], 'content': '추격자'}],
            }
        ],
    }


async def test_the_snapshot_of_a_minimal_scenario(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_ready_scenario(client, my_headers)

    version = await publish(client, my_headers, scenario)

    # 세계관과 로어북은 없어도 된다
    assert version['snapshot']['world'] is None
    assert version['snapshot']['lorebooks'] == []


# --- 판은 굳는다 ---


async def test_editing_the_draft_does_not_change_a_version(client: AsyncClient, my_headers: dict[str, str]):
    rulebook = await create(client, RULEBOOKS_URL, my_headers, gm_guide=GM_GUIDE)
    scenario = await create(client, SCENARIOS_URL, my_headers, rulebook_id=rulebook['id'], opening=OPENING)
    first = await publish(client, my_headers, scenario)

    # 게시한 뒤에 시나리오와 룰북을 둘 다 고친다
    await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'opening': '바뀐 도입부'}, headers=my_headers)
    await client.patch(f'{RULEBOOKS_URL}/{rulebook["id"]}', json={'gm_guide': '바뀐 지침'}, headers=my_headers)
    second = await publish(client, my_headers, scenario)

    first_again = (await client.get(f'{versions_url(scenario)}/1', headers=my_headers)).json()
    assert first_again == first
    assert first_again['snapshot']['opening'] == OPENING
    assert first_again['snapshot']['rulebook']['gm_guide'] == GM_GUIDE
    # 새 판에는 고친 내용이 들어간다
    assert second['snapshot']['opening'] == '바뀐 도입부'
    assert second['snapshot']['rulebook']['gm_guide'] == '바뀐 지침'


async def test_a_version_survives_detaching_and_deleting_its_assets(client: AsyncClient, my_headers: dict[str, str]):
    world = await create(client, WORLDS_URL, my_headers, setting=SETTING)
    scenario = await create_ready_scenario(client, my_headers, world_id=world['id'])
    version = await publish(client, my_headers, scenario)

    # 세계관을 떼고 지운다. 초안에서는 사라진다
    await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'world_id': None}, headers=my_headers)
    deleted = await client.delete(f'{WORLDS_URL}/{world["id"]}', headers=my_headers)

    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    again = (await client.get(f'{versions_url(scenario)}/1', headers=my_headers)).json()
    assert again == version
    assert again['snapshot']['world']['setting'] == SETTING


@pytest.mark.parametrize('method', ['PUT', 'PATCH', 'DELETE'])
async def test_a_version_has_no_address_to_change_it(client: AsyncClient, my_headers: dict[str, str], method: str):
    scenario = await create_ready_scenario(client, my_headers)
    await publish(client, my_headers, scenario)

    response = await client.request(method, f'{versions_url(scenario)}/1', json={'note': '바꿈'}, headers=my_headers)

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# --- 판 읽기 ---


async def test_lists_versions_newest_first_without_the_snapshot(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_ready_scenario(client, my_headers)
    await publish(client, my_headers, scenario, note='첫 판')
    await publish(client, my_headers, scenario, note='둘째 판')

    response = await client.get(versions_url(scenario), headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    versions = response.json()
    assert [(version['number'], version['note']) for version in versions] == [(2, '둘째 판'), (1, '첫 판')]
    # 목록에는 굳힌 내용을 싣지 않는다. 판 하나가 수백 KB 일 수 있다
    assert set(versions[0]) == {'id', 'number', 'note', 'created_at'}


async def test_reads_one_version_by_its_number(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_ready_scenario(client, my_headers)
    published = await publish(client, my_headers, scenario)

    found = await client.get(f'{versions_url(scenario)}/1', headers=my_headers)
    missing = await client.get(f'{versions_url(scenario)}/2', headers=my_headers)
    not_a_number = await client.get(f'{versions_url(scenario)}/latest', headers=my_headers)

    assert found.json() == published
    assert missing.status_code == status.HTTP_404_NOT_FOUND
    assert not_a_number.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 판은 만든 사람만 본다 ---


async def test_someone_elses_versions_look_like_they_do_not_exist(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    theirs = await create_ready_scenario(client, their_headers)
    await publish(client, their_headers, theirs)

    published = await client.post(versions_url(theirs), json={}, headers=my_headers)
    listed = await client.get(versions_url(theirs), headers=my_headers)
    read = await client.get(f'{versions_url(theirs)}/1', headers=my_headers)

    assert published.status_code == status.HTTP_404_NOT_FOUND
    assert listed.status_code == status.HTTP_404_NOT_FOUND
    assert read.status_code == status.HTTP_404_NOT_FOUND
    # GM 전용 글이 새어 나가지 않는다
    assert GM_GUIDE not in read.text
    assert len((await client.get(versions_url(theirs), headers=their_headers)).json()) == 1


async def test_a_version_cannot_be_read_through_another_scenario(client: AsyncClient, my_headers: dict[str, str]):
    published = await create_ready_scenario(client, my_headers)
    await publish(client, my_headers, published)
    unpublished = await create_ready_scenario(client, my_headers)

    # 판이 없는 시나리오의 주소로 1번 판을 읽는다
    response = await client.get(f'{versions_url(unpublished)}/1', headers=my_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_versions_of_a_deleted_scenario_cannot_be_reached(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_ready_scenario(client, my_headers)
    await publish(client, my_headers, scenario)
    await client.delete(f'{SCENARIOS_URL}/{scenario["id"]}', headers=my_headers)

    listed = await client.get(versions_url(scenario), headers=my_headers)
    published = await client.post(versions_url(scenario), json={}, headers=my_headers)

    assert listed.status_code == status.HTTP_404_NOT_FOUND
    assert published.status_code == status.HTTP_404_NOT_FOUND


# --- DB 의 마지막 방어선 ---


async def make_scenario(session: AsyncSession) -> uuid.UUID:
    """서비스를 거치지 않고 시나리오 하나를 저장한다."""
    scenario = Scenario(asset=Asset(owner_id=ME, type=AssetType.SCENARIO, title='시나리오'))
    session.add(scenario)
    await session.commit()
    return scenario.asset_id


async def test_the_database_rejects_two_versions_with_the_same_number(session: AsyncSession):
    scenario_id = await make_scenario(session)
    session.add(ScenarioVersion(scenario_id=scenario_id, number=1, snapshot={}))
    await session.commit()

    session.add(ScenarioVersion(scenario_id=scenario_id, number=1, snapshot={}))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_a_number_below_one(session: AsyncSession):
    scenario_id = await make_scenario(session)
    session.add(ScenarioVersion(scenario_id=scenario_id, number=0, snapshot={}))

    with pytest.raises(IntegrityError):
        await session.commit()
