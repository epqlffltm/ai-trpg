# trpg-server/tests/test_template_tables.py

"""
템플릿을 고르는 길(#615)을 API 로 검증한다. 템플릿의 파일과 판정은 tests/test_templates.py 가 본다.

보는 것.
  - 고를 수 있는 템플릿의 목록이 나온다. 로그인을 요구한다.
  - 고른 템플릿의 규칙이 룰북에 복사된다.
  - 템플릿마다 그 규칙으로 시나리오를 만들어 게시하고, 테이블을 열어 한 라운드를 판정할 수 있다.
  - 게시한 뒤에 템플릿이 바뀌어도 게시된 판과 그 판의 테이블은 그때의 규칙으로 돈다. 새로 만드는 룰북만 바뀐다.
  - 서술자는 그 판의 규칙의 서술 지침(#616)을 받는다. 같은 판정 결과라도 템플릿이 다르면 받는 지침이 다르다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient

from app.engine import templates
from app.engine.check import find_difficulty, modifier_of
from app.engine.dice import ScriptedDice
from app.engine.ruleset import Ruleset
from app.engine.templates import TEMPLATES, Template
from app.main import API_PREFIX
from app.rounds.narrator import NO_PREVIEW, NarrationRequest, Preview
from app.rounds.prompt import build_messages
from tests.narration_model import with_model
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TEMPLATES_URL = f'{RULEBOOKS_URL}/templates'
SCENARIOS_URL = f'{API_PREFIX}/scenarios'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')

OPENING = '사이렌이 울린다.'


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


def middle_score(rules: Ruleset) -> int:
    """점수의 범위 가운데의 점수."""
    return (rules.score_min + rules.score_max) // 2


def sheet_for(rules: Ruleset) -> dict:
    """그 규칙의 능력치를 모두 가운데 점수로 가진, 최대 HP 10 의 시트."""
    return {'abilities': {ability.key: middle_score(rules) for ability in rules.abilities}, 'max_hp': 10}


async def make_rulebook(client: AsyncClient, headers: dict[str, str], template: Template) -> dict:
    response = await client.post(RULEBOOKS_URL, json={'title': '룰북', 'template': template.value}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def publish(client: AsyncClient, headers: dict[str, str], template: Template) -> dict:
    """그 템플릿의 룰북으로 시나리오를 만들어 게시한다. 시나리오를 돌려준다."""
    rulebook = await make_rulebook(client, headers, template)
    rules = Ruleset.model_validate(rulebook['rules'])
    body = {'title': '추격전', 'rulebook_id': rulebook['id'], 'openings': [OPENING], 'default_sheet': sheet_for(rules)}
    created = await client.post(SCENARIOS_URL, json=with_model(body), headers=headers)
    assert created.status_code == status.HTTP_201_CREATED, created.text
    scenario = created.json()
    published = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=headers)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    return scenario


def table_url(table: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{table["id"]}{path}'


async def start_duo(client: AsyncClient, me: dict[str, str], friend: dict[str, str], scenario: dict) -> dict:
    """나와 친구가 앉은 테이블을 그 시나리오의 판 1 로 시작한다."""
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2}
    table = (await client.post(TABLES_URL, json=body, headers=me)).json()
    await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    await client.put(table_url(table, '/character'), json={'name': '영애'}, headers=friend)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table


async def declare_check(client: AsyncClient, headers: dict[str, str], table: dict, rules: Ruleset) -> dict:
    """그 규칙의 첫 능력치로 기본 난이도에 도전하는 선언을 내고, 돌아온 라운드를 돌려준다."""
    action = {'kind': 'check', 'ability': rules.abilities[0].key, 'difficulty': rules.default_difficulty}
    body = {'content': '문을 연다.', 'action': action}
    response = await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def outcome_of(round_: dict, name: str) -> dict:
    """라운드에서 그 캐릭터의 판정의 숫자."""
    declaration = next(item for item in round_['declarations'] if item['character_name'] == name)
    outcome = declaration['outcome']
    return {key: outcome[key] for key in ('roll', 'modifier', 'total', 'target', 'success')}


class WatchedDice:
    """굴릴 때마다 몇 면짜리를 굴리라고 했는지 적어 두는 주사위. 늘 1 을 낸다."""

    def __init__(self) -> None:
        self.asked: list[int] = []

    def roll(self, sides: int) -> int:
        self.asked.append(sides)
        return 1


class RecordingNarrator:
    """받은 부탁을 적어 두는 서술자."""

    def __init__(self) -> None:
        self.requests: list[NarrationRequest] = []

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        self.requests.append(request)
        return '문이 열렸다.'


# --- 목록 ---


async def test_the_list_requires_login(client: AsyncClient):
    response = await client.get(TEMPLATES_URL)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_the_list_carries_every_template_and_its_rules(client: AsyncClient, me: dict[str, str]):
    response = await client.get(TEMPLATES_URL, headers=me)

    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body['default'] == 'srd5'
    assert [item['key'] for item in body['items']] == ['srd5', 'horror', 'light']
    for item in body['items']:
        loaded = TEMPLATES[Template(item['key'])]
        assert item['name'] == loaded.name
        assert item['rules'] == loaded.rules.model_dump(mode='json')
    srd5 = body['items'][0]
    assert any('System Reference Document 5.1' in line for line in srd5['attribution'])


# --- 고른 템플릿이 룰북에 ---


@pytest.mark.parametrize('template', list(Template))
async def test_a_rulebook_copies_the_rules_of_its_template(client: AsyncClient, me: dict[str, str], template: Template):
    rulebook = await make_rulebook(client, me, template)

    assert rulebook['rules'] == TEMPLATES[template].rules.model_dump(mode='json')


# --- 템플릿마다 한 판 ---


@pytest.mark.parametrize('template', list(Template))
async def test_a_table_runs_a_round_on_every_template(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], template: Template
):
    rules = TEMPLATES[template].rules
    table = await start_duo(client, me, friend, await publish(client, me, template))
    difficulty = find_difficulty(rules, None)
    modifier = modifier_of(rules, middle_score(rules))
    needed = difficulty.target - modifier
    # 나는 목표에 꼭 맞는 눈, 친구는 한 눈 모자란 눈이다
    app.state.dice = ScriptedDice([needed, needed - 1])

    await declare_check(client, me, table, rules)
    closing = await declare_check(client, friend, table, rules)

    assert closing['status'] == 'closing'
    target = difficulty.target
    assert outcome_of(closing, '엘프') == {
        'roll': needed,
        'modifier': modifier,
        'total': target,
        'target': target,
        'success': True,
    }
    assert outcome_of(closing, '영애') == {
        'roll': needed - 1,
        'modifier': modifier,
        'total': target - 1,
        'target': target,
        'success': False,
    }


# --- 게시한 판은 그대로 ---


def changed_light() -> templates.TemplateFile:
    """가벼운 모험의 주사위만 d12 로 바꾼 템플릿. 템플릿이 바뀐 것으로 친다."""
    loaded = TEMPLATES[Template.LIGHT]
    return loaded.model_copy(update={'rules': loaded.rules.model_copy(update={'die': 12})})


async def test_a_published_version_keeps_the_rules_it_was_published_with(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    scenario = await publish(client, me, Template.LIGHT)

    monkeypatch.setitem(TEMPLATES, Template.LIGHT, changed_light())

    version = (await client.get(f'{SCENARIOS_URL}/{scenario["id"]}/versions/1', headers=me)).json()
    assert version['snapshot']['rulebook']['rules']['die'] == 10
    # 그 판의 테이블도 그때의 주사위(d10)를 굴린다
    table = await start_duo(client, me, friend, scenario)
    dice = WatchedDice()
    app.state.dice = dice
    rules = TEMPLATES[Template.LIGHT].rules
    await declare_check(client, me, table, rules)
    await declare_check(client, friend, table, rules)
    assert dice.asked == [10, 10]
    # 바뀐 템플릿은 새로 만드는 룰북에만 간다
    assert (await make_rulebook(client, me, Template.LIGHT))['rules']['die'] == 12


# --- 서술 지침(#616) ---


async def narrated_round(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated, template: Template
) -> NarrationRequest:
    """그 템플릿의 판에서 나는 꼭 맞는 눈으로 성공하고 친구는 한 눈 모자라 실패한 라운드를 서술하게 한다."""
    rules = TEMPLATES[template].rules
    table = await start_duo(client, me, friend, await publish(client, me, template))
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    needed = find_difficulty(rules, None).target - modifier_of(rules, middle_score(rules))
    app.state.dice = ScriptedDice([needed, needed - 1])
    await declare_check(client, me, table, rules)
    await declare_check(client, friend, table, rules)
    await narrated()
    (request,) = narrator.requests
    return request


async def test_the_narrator_gets_the_guide_of_the_rules_of_the_table(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    request = await narrated_round(client, app, me, friend, narrated, Template.HORROR)

    assert request.story.narration == TEMPLATES[Template.HORROR].rules.narration
    system = build_messages(request)[0].content
    assert TEMPLATES[Template.HORROR].rules.narration.tone in system


async def test_the_same_results_reach_two_templates_with_different_guides(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    fantasy = await narrated_round(client, app, me, friend, narrated, Template.SRD5)
    horror = await narrated_round(client, app, me, friend, narrated, Template.HORROR)

    # 판정 결과는 둘 다 성공 하나, 실패 하나다
    for request in (fantasy, horror):
        assert [move.verdict.success for move in request.moves] == [True, False]
    assert fantasy.story.narration != horror.story.narration
    assert build_messages(fantasy)[0].content != build_messages(horror)[0].content
