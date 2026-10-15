# game-server/tests/test_scenario_monsters.py

"""
시나리오의 몬스터(#231 1b)를 검증한다. 시나리오가 몬스터 도감을 붙이고 몬스터마다 시트를 적는다.

넷을 본다.
  - 시나리오: 도감과 몬스터 시트를 적고 읽고 고친다. 모양과 가리키는 도감만 본다.
  - 도감: 시나리오가 붙인 도감은 지울 수 없다. 몬스터는 지울 수 있다(게시할 때 걸린다).
  - 게시: 시트가 붙인 도감의 몬스터를 가리키는지, 규칙에 맞는지. 시트를 적은 몬스터만 판에 들어간다.
  - 판: 형식 21 에 실린다. 옛 판은 몬스터 없이 읽는다. 같은 몬스터가 두 번 있는 판은 받지 않는다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError

from app.assets.models import SCENARIO_MAX_BESTIARIES
from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT, Snapshot, read_snapshot
from app.assets.scenarios.upgrades import upgrade_from_20
from app.main import API_PREFIX
from tests.sheets import SHEET, make_sheet
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
BESTIARIES_URL = f'{API_PREFIX}/bestiaries'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

# 누구의 숫자인지 알아볼 수 있게 서로 다르게 둔다
RAT_SHEET = make_sheet(dex=14, max_hp=4)
SKELETON_SHEET = make_sheet(str=13, max_hp=13)


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 도감과 시나리오를 만드는 사람이다."""
    return bearer(signing_key, ME)


@pytest.fixture
def them(signing_key: SigningKey) -> dict[str, str]:
    """다른 사람의 토큰이 실린 머리말."""
    return bearer(signing_key, SOMEONE_ELSE)


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


async def post(client: AsyncClient, url: str, headers: dict[str, str], **body) -> dict:
    response = await client.post(url, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def add_monster(client: AsyncClient, headers: dict[str, str], bestiary: dict, name: str, kind: str) -> dict:
    url = f'{BESTIARIES_URL}/{bestiary["id"]}/monsters'
    return await post(client, url, headers, name=name, content=f'{name}의 설명', kind=kind)


@pytest.fixture
async def beasts(client: AsyncClient, me: dict[str, str]) -> dict:
    """몬스터 셋(수로 쥐, 해골 병사, 쓰지 않는 골렘)이 든 도감."""
    bestiary = await post(client, BESTIARIES_URL, me, title='지하 수로의 것들')
    return {
        'bestiary': bestiary,
        'rat': await add_monster(client, me, bestiary, '수로 쥐', 'beast'),
        'skeleton': await add_monster(client, me, bestiary, '해골 병사', 'undead'),
        'golem': await add_monster(client, me, bestiary, '돌 골렘', 'construct'),
    }


async def create_scenario(client: AsyncClient, headers: dict[str, str], beasts: dict | None, **fields) -> dict:
    """룰북, 스타팅, 기본 시트가 있는 시나리오. beasts 를 주면 그 도감을 붙인다."""
    rulebook = await post(client, RULEBOOKS_URL, headers, title='룰북')
    body = {
        'title': '지하 수로',
        'rulebook_id': rulebook['id'],
        'openings': ['물 떨어지는 소리가 난다.'],
        'default_sheet': SHEET,
        'bestiary_ids': [beasts['bestiary']['id']] if beasts else [],
    }
    body.update(fields)
    return await post(client, SCENARIOS_URL, headers, **body)


async def try_publish(client: AsyncClient, headers: dict[str, str], scenario: dict):
    return await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=headers)


async def refused(client: AsyncClient, headers: dict[str, str], scenario: dict) -> list[str]:
    """게시를 거절당한 이유들."""
    response = await try_publish(client, headers, scenario)
    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    return response.json()['problems']


async def published(client: AsyncClient, headers: dict[str, str], scenario: dict) -> dict:
    """게시한 판의 내용."""
    response = await try_publish(client, headers, scenario)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['snapshot']


def sheet_for(monster: dict, sheet: dict) -> dict:
    return {'monster_id': monster['id'], 'sheet': sheet}


# --- 시나리오: 적고 읽고 고친다 ---


async def test_bestiaries_and_monster_sheets_are_saved_and_read_back(
    client: AsyncClient, me: dict[str, str], beasts: dict
):
    scenario = await create_scenario(client, me, beasts, monster_sheets=[sheet_for(beasts['rat'], RAT_SHEET)])

    read = (await client.get(f'{SCENARIOS_URL}/{scenario["id"]}', headers=me)).json()

    assert read['bestiary_ids'] == [beasts['bestiary']['id']]
    assert read['monster_sheets'] == [sheet_for(beasts['rat'], RAT_SHEET)]


async def test_a_scenario_starts_without_bestiaries_or_monster_sheets(client: AsyncClient, me: dict[str, str]):
    scenario = await create_scenario(client, me, None)

    assert (scenario['bestiary_ids'], scenario['monster_sheets']) == ([], [])


@pytest.mark.parametrize(
    'fields',
    [
        # 같은 몬스터에 시트가 둘이면 어느 숫자를 쓸지 정할 수 없다
        {'monster_sheets': [sheet_for({'id': NO_SUCH_ID}, RAT_SHEET), sheet_for({'id': NO_SUCH_ID}, SHEET)]},
        # 시트를 비워 둘 수 없다. 숫자를 줄 생각이 없으면 칸을 만들지 않는다(이 시나리오는 그 몬스터를 쓰지 않는다)
        {'monster_sheets': [{'monster_id': NO_SUCH_ID}]},
        {'monster_sheets': [{'monster_id': NO_SUCH_ID, 'sheet': None}]},
        # 모양이 틀린 시트
        {'monster_sheets': [{'monster_id': NO_SUCH_ID, 'sheet': {'abilities': {}, 'max_hp': 0}}]},
        # 모르는 칸
        {'monster_sheets': [{'monster_id': NO_SUCH_ID, 'sheet': SHEET, 'count': 3}]},
        # 같은 도감이 두 번
        {'bestiary_ids': [NO_SUCH_ID, NO_SUCH_ID]},
        # 도감은 상한까지다
        {'bestiary_ids': [str(uuid.uuid4()) for _ in range(SCENARIO_MAX_BESTIARIES + 1)]},
    ],
)
async def test_rejects_bad_monster_fields(client: AsyncClient, me: dict[str, str], fields: dict):
    response = await client.post(SCENARIOS_URL, json={'title': '지하 수로', **fields}, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_only_my_own_bestiaries_can_be_attached(client: AsyncClient, me: dict[str, str], them: dict[str, str]):
    theirs = await post(client, BESTIARIES_URL, them, title='남의 도감')
    lorebook = await post(client, LOREBOOKS_URL, me, title='로어북')

    for bestiary_id in (theirs['id'], NO_SUCH_ID, lorebook['id']):
        response = await client.post(
            SCENARIOS_URL, json={'title': '지하 수로', 'bestiary_ids': [bestiary_id]}, headers=me
        )

        # 남의 도감, 없는 도감, 다른 종류의 자산은 모두 같은 답이다
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert 'bestiary_ids' in response.json()['detail']


async def test_updating_replaces_the_lists(client: AsyncClient, me: dict[str, str], beasts: dict):
    scenario = await create_scenario(client, me, beasts, monster_sheets=[sheet_for(beasts['rat'], RAT_SHEET)])
    other = await post(client, BESTIARIES_URL, me, title='무덤의 것들')
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    changed = await client.patch(
        url,
        json={'bestiary_ids': [other['id']], 'monster_sheets': [sheet_for(beasts['skeleton'], SKELETON_SHEET)]},
        headers=me,
    )
    cleared = await client.patch(url, json={'bestiary_ids': [], 'monster_sheets': []}, headers=me)

    assert changed.status_code == status.HTTP_200_OK
    assert changed.json()['bestiary_ids'] == [other['id']]
    assert changed.json()['monster_sheets'] == [sheet_for(beasts['skeleton'], SKELETON_SHEET)]
    assert (cleared.json()['bestiary_ids'], cleared.json()['monster_sheets']) == ([], [])


async def test_updating_without_the_fields_keeps_them(client: AsyncClient, me: dict[str, str], beasts: dict):
    scenario = await create_scenario(client, me, beasts, monster_sheets=[sheet_for(beasts['rat'], RAT_SHEET)])

    response = await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'title': '새 제목'}, headers=me)

    assert response.json()['bestiary_ids'] == [beasts['bestiary']['id']]
    assert response.json()['monster_sheets'] == [sheet_for(beasts['rat'], RAT_SHEET)]


# --- 도감: 붙인 동안은 지울 수 없다 ---


async def test_an_attached_bestiary_cannot_be_deleted(client: AsyncClient, me: dict[str, str], beasts: dict):
    scenario = await create_scenario(client, me, beasts)
    url = f'{BESTIARIES_URL}/{beasts["bestiary"]["id"]}'

    in_use = await client.delete(url, headers=me)
    await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'bestiary_ids': []}, headers=me)
    detached = await client.delete(url, headers=me)

    assert in_use.status_code == status.HTTP_409_CONFLICT
    assert in_use.json()['used_by'] == [{'id': scenario['id'], 'title': '지하 수로'}]
    assert detached.status_code == status.HTTP_204_NO_CONTENT


# --- 게시 ---


async def test_only_monsters_with_a_sheet_go_into_the_version(client: AsyncClient, me: dict[str, str], beasts: dict):
    sheets = [sheet_for(beasts['skeleton'], SKELETON_SHEET), sheet_for(beasts['rat'], RAT_SHEET)]
    scenario = await create_scenario(client, me, beasts, monster_sheets=sheets)

    snapshot = await published(client, me, scenario)

    assert snapshot['format'] == SNAPSHOT_FORMAT
    # 골렘은 시트가 없다. 이 시나리오가 쓰지 않는 몬스터다. 순서는 시트를 적은 순서다
    assert snapshot['monsters'] == [
        {
            'id': beasts['skeleton']['id'],
            'name': '해골 병사',
            'content': '해골 병사의 설명',
            'kind': 'undead',
            'sheet': SKELETON_SHEET,
        },
        {
            'id': beasts['rat']['id'],
            'name': '수로 쥐',
            'content': '수로 쥐의 설명',
            'kind': 'beast',
            'sheet': RAT_SHEET,
        },
    ]


async def test_a_scenario_without_monster_sheets_has_no_monsters(client: AsyncClient, me: dict[str, str], beasts: dict):
    # 도감을 붙였어도 시트를 적지 않았으면 몬스터가 없는 판이다
    snapshot = await published(client, me, await create_scenario(client, me, beasts))

    assert snapshot['monsters'] == []


async def test_a_version_keeps_the_monster_as_it_was(client: AsyncClient, me: dict[str, str], beasts: dict):
    scenario = await create_scenario(client, me, beasts, monster_sheets=[sheet_for(beasts['rat'], RAT_SHEET)])
    await published(client, me, scenario)
    monster_url = f'{BESTIARIES_URL}/{beasts["bestiary"]["id"]}/monsters/{beasts["rat"]["id"]}'
    await client.patch(monster_url, json={'name': '큰 쥐', 'kind': 'other'}, headers=me)

    first = (await client.get(f'{SCENARIOS_URL}/{scenario["id"]}/versions/1', headers=me)).json()['snapshot']

    # 판은 고치지 않는다. 도감을 고친 것은 다음 판에 들어간다
    assert (first['monsters'][0]['name'], first['monsters'][0]['kind']) == ('수로 쥐', 'beast')
    assert (await published(client, me, scenario))['monsters'][0]['name'] == '큰 쥐'


async def test_a_sheet_for_a_monster_of_an_unattached_bestiary_is_refused(
    client: AsyncClient, me: dict[str, str], beasts: dict
):
    other = await post(client, BESTIARIES_URL, me, title='무덤의 것들')
    ghost = await add_monster(client, me, other, '망령', 'undead')
    scenario = await create_scenario(client, me, beasts, monster_sheets=[sheet_for(ghost, SKELETON_SHEET)])

    assert await refused(client, me, scenario) == ['monster_sheet_missing']


async def test_detaching_the_bestiary_leaves_the_sheet_pointing_at_nothing(
    client: AsyncClient, me: dict[str, str], beasts: dict
):
    scenario = await create_scenario(client, me, beasts, monster_sheets=[sheet_for(beasts['rat'], RAT_SHEET)])
    await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'bestiary_ids': []}, headers=me)

    assert await refused(client, me, scenario) == ['monster_sheet_missing']


async def test_deleting_a_monster_with_a_sheet_is_caught_when_publishing(
    client: AsyncClient, me: dict[str, str], beasts: dict
):
    scenario = await create_scenario(client, me, beasts, monster_sheets=[sheet_for(beasts['rat'], RAT_SHEET)])
    monster_url = f'{BESTIARIES_URL}/{beasts["bestiary"]["id"]}/monsters/{beasts["rat"]["id"]}'

    # 몬스터는 행을 실제로 지운다. 시나리오가 쓰고 있어도 막지 않고, 게시할 때 알려 준다
    deleted = await client.delete(monster_url, headers=me)

    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    assert await refused(client, me, scenario) == ['monster_sheet_missing']


@pytest.mark.parametrize('sheet', [make_sheet(str=21), {'abilities': {'str': 10}, 'max_hp': 5}])
async def test_monster_sheets_must_fit_the_rules(client: AsyncClient, me: dict[str, str], beasts: dict, sheet: dict):
    scenario = await create_scenario(client, me, beasts, monster_sheets=[sheet_for(beasts['rat'], sheet)])

    assert await refused(client, me, scenario) == ['monster_sheet_invalid']


async def test_every_problem_of_the_monster_sheets_is_told_at_once(
    client: AsyncClient, me: dict[str, str], beasts: dict
):
    sheets = [sheet_for({'id': NO_SUCH_ID}, RAT_SHEET), sheet_for(beasts['rat'], make_sheet(str=21))]
    scenario = await create_scenario(client, me, beasts, monster_sheets=sheets)

    assert await refused(client, me, scenario) == ['monster_sheet_missing', 'monster_sheet_invalid']


async def test_without_a_rulebook_monster_sheets_are_not_checked_against_rules(
    client: AsyncClient, me: dict[str, str], beasts: dict
):
    sheets = [sheet_for(beasts['rat'], make_sheet(str=21))]
    scenario = await create_scenario(client, me, beasts, rulebook_id=None, monster_sheets=sheets)

    assert await refused(client, me, scenario) == ['rulebook_missing']


# --- 판: 계약과 옛 판 ---


async def test_a_snapshot_with_the_same_monster_twice_is_invalid(client: AsyncClient, me: dict[str, str], beasts: dict):
    scenario = await create_scenario(client, me, beasts, monster_sheets=[sheet_for(beasts['rat'], RAT_SHEET)])
    document = await published(client, me, scenario)

    # 입력이 막는 것을 판의 계약도 막는다. 읽는 쪽은 몬스터의 id 로 하나를 찾는다
    with pytest.raises(ValidationError):
        Snapshot.model_validate({**document, 'monsters': document['monsters'] * 2})


async def test_upgrades_a_format_20_document(client: AsyncClient, me: dict[str, str]):
    current = await published(client, me, await create_scenario(client, me, None))
    format_20 = {key: value for key, value in current.items() if key != 'monsters'}
    format_20['format'] = 20

    upgraded = upgrade_from_20(format_20)

    # 몬스터가 없던 때의 판이다
    assert (upgraded['format'], upgraded['monsters']) == (21, [])
    assert 'monsters' not in format_20
    assert read_snapshot(format_20).monsters == []
