# game-server/tests/test_versions_api.py

"""
시나리오의 게시를 검증한다.

게시는 초안의 지금 내용을 판으로 굳히는 일이다. 보는 것은 다섯이다.
  - 조건을 갖춘 시나리오만 게시된다. 못 갖췄으면 이유를 전부 알려 준다.
  - 판에는 시나리오와 그것이 가리키는 자산의 내용이 통째로 들어간다.
  - 판은 굳는다. 게시한 뒤에 초안을 고치거나 지워도 판은 그대로다.
  - 판은 만든 사람만 본다.
  - 옛 형식으로 굳힌 판도 지금의 모양으로 읽힌다. 저장된 것은 바뀌지 않는다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import (
    TABLE_MAX_PLAYERS,
    VERSION_NOTE_MAX_LENGTH,
    Asset,
    AssetType,
    LoreKind,
    Scenario,
    ScenarioVersion,
)
from app.assets.scenarios.snapshot import (
    SNAPSHOT_FORMAT,
    read_snapshot,
    upgrade_from_1,
    upgrade_from_2,
    upgrade_from_3,
    upgrade_from_4,
    upgrade_from_5,
    upgrade_from_6,
    upgrade_from_7,
    upgrade_from_8,
    upgrade_from_9,
    upgrade_from_10,
    upgrade_from_11,
)
from app.engine.sheet import fits
from app.engine.templates import SRD5
from app.main import API_PREFIX
from tests.sheets import SHEET, make_sheet
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
NPC_SHEET = make_sheet(str=16, max_hp=22)
PREGENS = [{'name': '폭주족 엘프', 'description': '귀가 길어서 헬멧을 못 쓴다.', 'sheet': make_sheet(dex=16, max_hp=8)}]


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
    """게시할 조건을 갖춘 시나리오를 만든다. 룰북이 붙어 있고, 스타팅이 하나 있고, 기본 시트가 있다."""
    rulebook = await create(client, RULEBOOKS_URL, headers, title='룰북', gm_guide=GM_GUIDE)
    values = {'rulebook_id': rulebook['id'], 'openings': [OPENING], 'default_sheet': SHEET}
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
    scenario = await create(client, SCENARIOS_URL, my_headers, openings=[OPENING], default_sheet=SHEET)

    response = await client.post(versions_url(scenario), json={}, headers=my_headers)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['rulebook_missing']
    assert (await client.get(versions_url(scenario), headers=my_headers)).json() == []


async def test_a_scenario_without_an_opening_cannot_be_published(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_ready_scenario(client, my_headers, openings=[])

    response = await client.post(versions_url(scenario), json={}, headers=my_headers)

    # 스타팅이 하나는 있어야 한다. 테이블이 시작할 장면이 없다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['opening_missing']


async def test_the_refusal_lists_every_problem(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create(client, SCENARIOS_URL, my_headers)

    response = await client.post(versions_url(scenario), json={}, headers=my_headers)

    # 하나씩 고치고 다시 시도하지 않게 한 번에 알려 준다
    assert response.json()['problems'] == ['rulebook_missing', 'opening_missing', 'default_sheet_missing']


async def test_the_rating_comes_from_the_scenario_alone(client: AsyncClient, my_headers: dict[str, str]):
    world = await create(client, WORLDS_URL, my_headers)
    all_ages = await create_ready_scenario(client, my_headers, world_id=world['id'])
    adult = await create_ready_scenario(client, my_headers, world_id=world['id'], rating='adult')

    # 등급은 시나리오를 조립할 때 제작자가 정한다. 같은 재료로 전체 이용가와 성인용을 둘 다 만들 수 있다
    assert (await publish(client, my_headers, all_ages))['snapshot']['rating'] == 'all'
    assert (await publish(client, my_headers, adult))['snapshot']['rating'] == 'adult'


async def test_fixing_the_problems_lets_it_publish(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create(client, SCENARIOS_URL, my_headers)
    rulebook = await create(client, RULEBOOKS_URL, my_headers)
    await client.patch(
        f'{SCENARIOS_URL}/{scenario["id"]}',
        json={'rulebook_id': rulebook['id'], 'openings': [OPENING], 'default_sheet': SHEET},
        headers=my_headers,
    )

    version = await publish(client, my_headers, scenario)

    assert version['number'] == 1


# --- 게시할 조건: 시트 ---


async def refused(client: AsyncClient, headers: dict[str, str], scenario: dict) -> list[str]:
    """게시를 시도해서 거절당하고, 그 이유들을 돌려준다."""
    response = await client.post(versions_url(scenario), json={}, headers=headers)
    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    return response.json()['problems']


async def test_allowing_custom_characters_needs_a_default_sheet(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_ready_scenario(client, my_headers, default_sheet=None)

    # 캐릭터를 직접 만든 사람이 받을 숫자가 없다
    assert await refused(client, my_headers, scenario) == ['default_sheet_missing']


async def test_pregens_alone_need_no_default_sheet(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_ready_scenario(
        client, my_headers, default_sheet=None, character_modes=['pregen'], pregens=PREGENS
    )

    version = await publish(client, my_headers, scenario)

    assert version['snapshot']['character_modes'] == ['pregen']
    assert version['snapshot']['default_sheet'] is None


@pytest.mark.parametrize(
    'sheet',
    [
        # 능력치가 하나 빠졌다
        {'abilities': {'str': 10, 'dex': 10, 'con': 10, 'int': 10, 'wis': 10}, 'max_hp': 10},
        # 규칙에 없는 능력치가 있다
        {'abilities': {**SHEET['abilities'], 'luck': 10}, 'max_hp': 10},
        # 점수가 범위(1~20) 밖이다
        make_sheet(str=21),
        make_sheet(str=0),
    ],
)
async def test_a_sheet_must_fit_the_rules_of_the_rulebook(client: AsyncClient, my_headers: dict[str, str], sheet: dict):
    as_default = await create_ready_scenario(client, my_headers, default_sheet=sheet)
    as_pregen = await create_ready_scenario(client, my_headers, pregens=[{'name': '엘프', 'sheet': sheet}])

    # 모양은 맞아서 저장은 됐다. 규칙에 맞는지는 룰북이 정해진 지금 본다
    assert await refused(client, my_headers, as_default) == ['default_sheet_invalid']
    assert await refused(client, my_headers, as_pregen) == ['pregen_sheet_invalid']


async def test_every_pregen_needs_a_sheet(client: AsyncClient, my_headers: dict[str, str]):
    pregens = [{'name': '엘프', 'sheet': SHEET}, {'name': '드워프'}, {'name': '악역영애'}]
    scenario = await create_ready_scenario(client, my_headers, pregens=pregens)

    # 둘이 빠졌어도 같은 이유는 한 번만 적는다
    assert await refused(client, my_headers, scenario) == ['pregen_sheet_missing']


async def test_pregens_are_checked_even_when_they_cannot_be_picked(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_ready_scenario(client, my_headers, character_modes=['custom'], pregens=[{'name': '엘프'}])

    # 판 안의 프리젠은 어느 것이든 시트가 있다. 쓰지 않을 프리젠은 지우고 게시한다
    assert await refused(client, my_headers, scenario) == ['pregen_sheet_missing']


async def test_a_default_sheet_is_checked_even_when_it_is_not_needed(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_ready_scenario(
        client, my_headers, character_modes=['pregen'], pregens=PREGENS, default_sheet=make_sheet(str=21)
    )

    assert await refused(client, my_headers, scenario) == ['default_sheet_invalid']


async def test_without_a_rulebook_sheets_are_only_checked_for_being_there(
    client: AsyncClient, my_headers: dict[str, str]
):
    scenario = await create(
        client,
        SCENARIOS_URL,
        my_headers,
        openings=[OPENING],
        default_sheet=make_sheet(str=21),
        pregens=[{'name': '엘프'}],
    )

    # 규칙이 없으니 맞는지는 볼 수 없다. 룰북을 붙이고 다시 게시하면 그때 나온다
    assert await refused(client, my_headers, scenario) == ['rulebook_missing', 'pregen_sheet_missing']


@pytest.mark.parametrize(('count', 'problems'), [(1, ['pregens_too_few']), (2, None), (3, None)])
async def test_pregens_alone_must_seat_the_fewest_recommended_players(
    client: AsyncClient, my_headers: dict[str, str], count: int, problems: list[str] | None
):
    pregens = [{'name': f'{number}번', 'sheet': SHEET} for number in range(count)]
    scenario = await create_ready_scenario(
        client, my_headers, character_modes=['pregen'], pregens=pregens, recommended_players={'min': 2, 'max': 4}
    )

    response = await client.post(versions_url(scenario), json={}, headers=my_headers)

    # 프리젠 하나는 한 사람만 고른다. 프리젠만 허용했으면 프리젠의 수가 앉을 수 있는 사람의 수다
    assert response.json().get('problems') == problems


async def test_few_pregens_are_fine_when_characters_can_also_be_made(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_ready_scenario(
        client, my_headers, pregens=[{'name': '엘프', 'sheet': SHEET}], recommended_players={'min': 3, 'max': 4}
    )

    assert (await publish(client, my_headers, scenario))['number'] == 1


# --- 판에 들어가는 것 ---


async def test_the_snapshot_carries_everything_needed_to_play(client: AsyncClient, my_headers: dict[str, str]):
    rulebook = await create(client, RULEBOOKS_URL, my_headers, title='룰북', gm_guide=GM_GUIDE)
    world = await create(client, WORLDS_URL, my_headers, title='세계관', setting=SETTING, gm_notes=GM_NOTES)
    lorebook = await create(client, LOREBOOKS_URL, my_headers, title='인명사전')
    entries_url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    entry = (
        await client.post(
            entries_url,
            json={'name': '스미스', 'keywords': ['드워프'], 'content': '추격자', 'kind': 'person'},
            headers=my_headers,
        )
    ).json()
    scenario = await create(
        client,
        SCENARIOS_URL,
        my_headers,
        description='메모',
        rulebook_id=rulebook['id'],
        world_id=world['id'],
        lorebook_ids=[lorebook['id']],
        openings=[OPENING],
        recommended_players={'min': 2, 'max': 3},
        pregens=PREGENS,
        default_sheet=SHEET,
        npc_sheets=[{'entry_id': entry['id'], 'sheet': NPC_SHEET}],
    )

    version = await publish(client, my_headers, scenario)

    assert version['snapshot'] == {
        'format': SNAPSHOT_FORMAT,
        'title': TITLE,
        'description': '메모',
        'rating': 'all',
        'openings': [OPENING],
        'recommended_players': {'min': 2, 'max': 3},
        'pregens': PREGENS,
        'character_modes': ['pregen', 'custom'],
        'default_sheet': SHEET,
        # 인물 항목이 모두 시트를 가졌다. 기본 NPC 시트는 없어도 된다
        'npc_sheets': [{'entry_id': entry['id'], 'sheet': NPC_SHEET}],
        'default_npc_sheet': None,
        'player_made_hp': None,
        'reroll_allowed': False,
        'narration_style': 'classic',
        'rulebook': {'id': rulebook['id'], 'title': '룰북', 'gm_guide': GM_GUIDE, 'rules': rulebook['rules']},
        'world': {'id': world['id'], 'title': '세계관', 'setting': SETTING, 'gm_notes': GM_NOTES},
        'lorebooks': [
            {
                'id': lorebook['id'],
                'title': '인명사전',
                'entries': [
                    {'id': entry['id'], 'name': '스미스', 'keywords': ['드워프'], 'content': '추격자', 'kind': 'person'}
                ],
            }
        ],
    }


async def test_the_recommended_style_is_frozen_into_the_version(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_ready_scenario(client, my_headers, narration_style='literary')
    first = await publish(client, my_headers, scenario)

    await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'narration_style': 'dopamine'}, headers=my_headers)
    second = await publish(client, my_headers, scenario)
    reread = await client.get(f'{versions_url(scenario)}/1', headers=my_headers)

    # 판에 굳는다. 제작자가 나중에 추천을 바꿔도 먼저 낸 판(과 그 판으로 도는 테이블)은 그대로다
    assert first['snapshot']['narration_style'] == 'literary'
    assert second['snapshot']['narration_style'] == 'dopamine'
    assert reread.json()['snapshot']['narration_style'] == 'literary'


async def test_the_snapshot_of_a_minimal_scenario(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_ready_scenario(client, my_headers)

    version = await publish(client, my_headers, scenario)

    # 세계관과 로어북은 없어도 된다
    assert version['snapshot']['world'] is None
    assert version['snapshot']['lorebooks'] == []
    # 추천 인원을 적지 않았으면 몇 명이든 된다는 뜻이다. 프리젠도 없어도 된다
    assert version['snapshot']['recommended_players'] == {'min': 1, 'max': TABLE_MAX_PLAYERS}
    assert version['snapshot']['pregens'] == []


async def test_the_snapshot_carries_every_opening_in_order(client: AsyncClient, my_headers: dict[str, str]):
    openings = ['추격전으로 시작', '법정에서 시작', '꿈에서 시작']
    scenario = await create_ready_scenario(client, my_headers, openings=openings)

    version = await publish(client, my_headers, scenario)

    # 테이블을 만드는 사람이 이 중 하나를 순번으로 고른다
    assert version['snapshot']['openings'] == openings


# --- 판은 굳는다 ---


async def test_editing_the_draft_does_not_change_a_version(client: AsyncClient, my_headers: dict[str, str]):
    rulebook = await create(client, RULEBOOKS_URL, my_headers, gm_guide=GM_GUIDE)
    scenario = await create(
        client, SCENARIOS_URL, my_headers, rulebook_id=rulebook['id'], openings=[OPENING], default_sheet=SHEET
    )
    first = await publish(client, my_headers, scenario)

    # 게시한 뒤에 시나리오와 룰북을 둘 다 고친다
    await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'openings': ['바뀐 도입부']}, headers=my_headers)
    await client.patch(f'{RULEBOOKS_URL}/{rulebook["id"]}', json={'gm_guide': '바뀐 지침'}, headers=my_headers)
    second = await publish(client, my_headers, scenario)

    first_again = (await client.get(f'{versions_url(scenario)}/1', headers=my_headers)).json()
    assert first_again == first
    assert first_again['snapshot']['openings'] == [OPENING]
    assert first_again['snapshot']['rulebook']['gm_guide'] == GM_GUIDE
    # 새 판에는 고친 내용이 들어간다
    assert second['snapshot']['openings'] == ['바뀐 도입부']
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


# --- 옛 형식의 판 ---

# 형식 1 로 굳힌 판의 문서. 도입부가 하나(opening)였다
FORMAT_1 = {
    'format': 1,
    'title': TITLE,
    'description': '',
    'rating': 'all',
    'opening': OPENING,
    'rulebook': {'id': NO_SUCH_ID, 'title': '룰북', 'gm_guide': GM_GUIDE},
    'world': None,
    'lorebooks': [],
}


def test_upgrades_a_format_1_document():
    upgraded = upgrade_from_1(FORMAT_1)

    # 하나뿐이던 도입부가 첫 번째 스타팅이 된다
    assert upgraded['format'] == 2
    assert upgraded['openings'] == [OPENING]
    assert 'opening' not in upgraded
    # 받은 문서는 고치지 않는다
    assert FORMAT_1['format'] == 1
    assert 'openings' not in FORMAT_1


def test_upgrades_a_format_2_document():
    format_2 = upgrade_from_1(FORMAT_1)

    upgraded = upgrade_from_2(format_2)

    # 추천 인원과 프리젠이 없던 때의 판이다. "몇 명이든 된다", "프리젠 없음"으로 읽는다
    assert upgraded['format'] == 3
    assert upgraded['recommended_players'] == {'min': 1, 'max': TABLE_MAX_PLAYERS}
    assert upgraded['pregens'] == []
    assert upgraded['openings'] == [OPENING]
    # 받은 문서는 고치지 않는다
    assert format_2['format'] == 2
    assert 'pregens' not in format_2


def test_upgrades_a_format_3_document():
    format_3 = upgrade_from_2(upgrade_from_1(FORMAT_1))

    upgraded = upgrade_from_3(format_3)

    # 룰북에 규칙이 없던 때의 판이다. 그때 만든 룰북이 받았을 규칙(SRD5 템플릿)으로 읽는다
    assert upgraded['format'] == 4
    assert upgraded['rulebook']['rules'] == SRD5.model_dump(mode='json')
    assert upgraded['rulebook']['gm_guide'] == GM_GUIDE
    # 받은 문서는 고치지 않는다. 안쪽의 룰북도 그대로다
    assert format_3['format'] == 3
    assert 'rules' not in format_3['rulebook']


def test_upgrades_a_format_4_document():
    format_3 = upgrade_from_2(upgrade_from_1(FORMAT_1))
    format_4 = upgrade_from_3({**format_3, 'pregens': [{'name': '엘프', 'description': ''}]})

    upgraded = upgrade_from_4(format_4)

    # 캐릭터에 숫자가 없던 때의 판이다. 두 방식을 모두 허용한 것으로, 시트는 기준 시트(모두 10, HP 10)로 읽는다
    assert upgraded['format'] == 5
    assert upgraded['character_modes'] == ['pregen', 'custom']
    assert upgraded['default_sheet'] == SHEET
    assert upgraded['pregens'] == [{'name': '엘프', 'description': '', 'sheet': SHEET}]
    # 받은 문서는 고치지 않는다. 안쪽의 프리젠도 그대로다
    assert format_4['format'] == 4
    assert 'sheet' not in format_4['pregens'][0]
    assert 'default_sheet' not in format_4


def without_rules(document: dict, *names: str) -> dict:
    """판의 규칙에서 칸 몇 개를 뺀 문서. 그 칸이 생기기 전에 DB 에 굳은 문서의 모양이다."""
    rules = {key: value for key, value in document['rulebook']['rules'].items() if key not in names}
    return {**document, 'rulebook': {**document['rulebook'], 'rules': rules}}


def make_format_5() -> dict:
    """양의 등급이 없던 때의 판."""
    document = upgrade_from_4(upgrade_from_3(upgrade_from_2(upgrade_from_1(FORMAT_1))))
    return without_rules(document, 'magnitudes', 'hp_ability', 'point_buy', 'score_roll', 'death_save')


def make_format_6() -> dict:
    """최대 HP 에 닿는 능력치가 없던 때의 판."""
    return without_rules(upgrade_from_5(make_format_5()), 'hp_ability', 'point_buy', 'score_roll', 'death_save')


def make_format_7() -> dict:
    """점수제가 없던 때의 판."""
    return without_rules(upgrade_from_6(make_format_6()), 'point_buy', 'score_roll', 'death_save')


def make_format_8() -> dict:
    """점수를 주사위로 정하는 법이 없던 때의 판."""
    return without_rules(upgrade_from_7(make_format_7()), 'score_roll', 'death_save')


def make_format_9() -> dict:
    """죽음의 굴림이 없던 때의 판."""
    return without_rules(upgrade_from_8(make_format_8()), 'death_save')


def make_format_10() -> dict:
    """추천 문체가 없던 때의 판."""
    return {key: value for key, value in upgrade_from_9(make_format_9()).items() if key != 'narration_style'}


def make_format_11() -> dict:
    """로어북 항목에 종류가 없던 때의 판. 항목 하나가 든 로어북이 붙어 있다."""
    entry = {'id': NO_SUCH_ID, 'name': '스미스', 'keywords': ['드워프'], 'content': '추격자'}
    return {
        **upgrade_from_10(make_format_10()),
        'lorebooks': [{'id': NO_SUCH_ID, 'title': '인명사전', 'entries': [entry]}],
    }


def test_upgrades_a_format_5_document():
    format_5 = make_format_5()

    upgraded = upgrade_from_5(format_5)

    # 규칙에 양의 등급이 없던 때의 판이다. 그때의 규칙(SRD5 템플릿)의 등급으로 읽는다
    assert upgraded['format'] == 6
    assert upgraded['rulebook']['rules']['magnitudes'] == SRD5.model_dump(mode='json')['magnitudes']
    assert upgraded['rulebook']['gm_guide'] == GM_GUIDE
    # 받은 문서는 고치지 않는다. 안쪽의 규칙도 그대로다
    assert format_5['format'] == 5
    assert 'magnitudes' not in format_5['rulebook']['rules']


def test_upgrades_a_format_6_document():
    format_6 = make_format_6()

    upgraded = upgrade_from_6(format_6)

    # 규칙에 최대 HP 에 닿는 능력치가 없던 때의 판이다. 그때의 규칙(SRD5 템플릿)의 것으로 읽는다
    assert upgraded['format'] == 7
    assert upgraded['rulebook']['rules']['hp_ability'] == 'con'
    # 플레이어가 능력치를 정하는 방식도 없던 때다. 그 방식에 쓰는 값은 없는 것으로 읽는다
    assert upgraded['player_made_hp'] is None
    # 받은 문서는 고치지 않는다
    assert format_6['format'] == 6
    assert 'hp_ability' not in format_6['rulebook']['rules']


def test_upgrades_a_format_7_document():
    format_7 = make_format_7()

    upgraded = upgrade_from_7(format_7)

    # 규칙에 점수제가 없던 때의 판이다. 그때의 규칙(SRD5 템플릿)의 것으로 읽는다
    assert upgraded['format'] == 8
    assert upgraded['rulebook']['rules']['point_buy'] == SRD5.model_dump(mode='json')['point_buy']
    assert upgraded['rulebook']['gm_guide'] == GM_GUIDE
    # 규칙에 점수제가 생겼다고 그 판에서 점수제를 쓸 수 있게 된 것은 아니다. 허용한 방식은 그대로다
    assert upgraded['character_modes'] == format_7['character_modes'] == ['pregen', 'custom']
    # 받은 문서는 고치지 않는다
    assert format_7['format'] == 7
    assert 'point_buy' not in format_7['rulebook']['rules']


def test_upgrades_a_format_8_document():
    format_8 = make_format_8()

    upgraded = upgrade_from_8(format_8)

    # 규칙에 점수를 주사위로 정하는 법이 없던 때의 판이다. 그때의 규칙(SRD5 템플릿)의 것으로 읽는다
    assert upgraded['format'] == 9
    assert upgraded['rulebook']['rules']['score_roll'] == SRD5.model_dump(mode='json')['score_roll']
    assert upgraded['rulebook']['gm_guide'] == GM_GUIDE
    # 규칙에 그 법이 생겼다고 그 판에서 주사위로 정할 수 있게 된 것은 아니다. 허용한 방식은 그대로다
    assert upgraded['character_modes'] == format_8['character_modes'] == ['pregen', 'custom']
    # 주사위로 정하는 방식이 없었으니 다시 굴리기도 없었다
    assert upgraded['reroll_allowed'] is False
    # 받은 문서는 고치지 않는다
    assert format_8['format'] == 8
    assert 'score_roll' not in format_8['rulebook']['rules']


def test_upgrades_a_format_9_document():
    format_9 = make_format_9()

    upgraded = upgrade_from_9(format_9)

    # 규칙에 죽음의 굴림이 없던 때의 판이다. 그때의 규칙(SRD5 템플릿)의 것으로 읽는다
    assert upgraded['format'] == 10
    assert upgraded['rulebook']['rules'] == SRD5.model_dump(mode='json')
    assert upgraded['rulebook']['gm_guide'] == GM_GUIDE
    # 받은 문서는 고치지 않는다
    assert format_9['format'] == 9
    assert 'death_save' not in format_9['rulebook']['rules']


def test_upgrades_a_format_10_document():
    format_10 = make_format_10()

    upgraded = upgrade_from_10(format_10)

    # 추천 문체가 없던 때의 판이다. 제작자가 고르지 않았을 때와 같은 정통으로 읽는다
    assert upgraded['format'] == 11
    assert upgraded['narration_style'] == 'classic'
    # 받은 문서는 고치지 않는다
    assert format_10['format'] == 10
    assert 'narration_style' not in format_10


def test_upgrades_a_format_11_document():
    format_11 = make_format_11()

    upgraded = upgrade_from_11(format_11)

    # 항목에 종류가 없던 때의 판이다. 지금까지와 똑같이 다뤄지는 기타로 읽는다
    assert upgraded['format'] == 12
    (entry,) = upgraded['lorebooks'][0]['entries']
    assert entry == {**format_11['lorebooks'][0]['entries'][0], 'kind': 'other'}
    assert upgraded['lorebooks'][0]['title'] == '인명사전'
    # 받은 문서는 고치지 않는다. 안쪽의 항목도 그대로다
    assert format_11['format'] == 11
    assert 'kind' not in format_11['lorebooks'][0]['entries'][0]


def test_reads_a_version_from_before_lore_kinds():
    old = read_snapshot(make_format_11())

    assert old.format == SNAPSHOT_FORMAT
    assert [entry.kind for lorebook in old.lorebooks for entry in lorebook.entries] == [LoreKind.OTHER]


def test_reads_a_version_from_before_narration_styles():
    old = read_snapshot(make_format_10())

    assert old.format == SNAPSHOT_FORMAT
    assert old.narration_style == 'classic'


def test_reads_a_version_from_before_death_saves():
    old = read_snapshot(make_format_9())

    assert old.format == SNAPSHOT_FORMAT
    assert old.rulebook.rules.death_save == SRD5.death_save


def test_reads_a_version_from_before_score_rolls():
    old = read_snapshot(make_format_8())

    assert old.format == SNAPSHOT_FORMAT
    assert old.rulebook.rules.score_roll == SRD5.score_roll


def test_reads_a_version_from_before_point_buy():
    old = read_snapshot(make_format_7())

    assert old.format == SNAPSHOT_FORMAT
    assert old.rulebook.rules.point_buy == SRD5.point_buy


def test_reads_a_version_from_before_magnitudes():
    old = read_snapshot(make_format_5())

    assert [magnitude.key for magnitude in old.rulebook.rules.magnitudes] == ['light', 'moderate', 'heavy']


def test_the_sheets_of_an_old_version_fit_its_rules():
    old = read_snapshot(FORMAT_1)

    # 옛 판에 채워 넣은 시트도 그 판의 규칙에 맞는다. 판 안의 시트는 어느 것이든 규칙에 맞아야 한다
    assert old.default_sheet is not None
    assert fits(old.rulebook.rules, old.default_sheet)


def test_reads_a_document_of_any_format():
    current = upgrade_from_1(FORMAT_1)

    # 옛 형식은 올려서, 지금 형식은 그대로 읽는다. 결과가 같다
    assert read_snapshot(FORMAT_1) == read_snapshot(current)
    assert read_snapshot(FORMAT_1).format == SNAPSHOT_FORMAT
    assert read_snapshot(FORMAT_1).openings == [OPENING]
    # 형식 1 은 1 → 2 → … → 11 을 차례로 거친다
    assert read_snapshot(FORMAT_1).pregens == []
    assert read_snapshot(FORMAT_1).rulebook.rules == SRD5


async def test_a_version_in_the_old_format_is_read_in_the_current_one(
    client: AsyncClient, my_headers: dict[str, str], session: AsyncSession
):
    scenario = await create_ready_scenario(client, my_headers)
    # 형식이 바뀌기 전에 굳힌 판을 흉내 낸다. 서비스를 거치지 않고 옛 문서를 그대로 저장한다
    session.add(ScenarioVersion(scenario_id=uuid.UUID(scenario['id']), number=1, snapshot=FORMAT_1))
    await session.commit()

    response = await client.get(f'{versions_url(scenario)}/1', headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['snapshot']['format'] == SNAPSHOT_FORMAT
    assert response.json()['snapshot']['openings'] == [OPENING]
    assert response.json()['snapshot']['rulebook']['rules'] == SRD5.model_dump(mode='json')
    # 저장된 문서는 옛 모양 그대로다. 판은 고치지 않는다
    stored = await session.scalar(
        text('SELECT snapshot FROM scenario_versions WHERE scenario_id = :id'), {'id': scenario['id']}
    )
    assert stored == FORMAT_1


async def test_the_next_version_after_an_old_one_uses_the_current_format(
    client: AsyncClient, my_headers: dict[str, str], session: AsyncSession
):
    scenario = await create_ready_scenario(client, my_headers)
    session.add(ScenarioVersion(scenario_id=uuid.UUID(scenario['id']), number=1, snapshot=FORMAT_1))
    await session.commit()

    second = await publish(client, my_headers, scenario)

    assert second['number'] == 2
    assert second['snapshot']['format'] == SNAPSHOT_FORMAT


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
