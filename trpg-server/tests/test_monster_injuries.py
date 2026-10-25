# trpg-server/tests/test_monster_injuries.py

"""
몬스터도 부상을 입는 것과, 부상의 성질에 따른 면역(#799)을 검증한다.

맵은 수로 입구 하나다. 입구에 수로 쥐 하나(야수, 최대 HP 4)와 해골 병사 하나(언데드, 최대 HP 4)가 있다.
룰북은 SRD5 다. 부상 표는 이십면체이고, 11 은 기절(stun), 17 은 팔 골절(body)이다.
주사위는 판정의 눈, 피해의 양, (큰 타격이나 쓰러짐이면) 부상 표의 눈 차례다. 노려 쳤으면 부상 표를 굴리지 않는다.

보는 것.
  - 라운드: 큰 타격에 부상 표를 굴려 그 마리가 입는다. 노려 친 타격이 맞으면 그 부상이 생긴다.
    장면에 입은 부상이 보이고, injury_gained 에 그 마리의 id 가 있다. 짧은 부상은 때가 되면 풀린다(injury_ended).
  - 면역: 그 성질의 부상은 입지 않는다(문서의 immune). 노려 칠 수 없다(target_immune). 이미 입은 부상도 노릴 수 없다.
    면역은 타입의 성질표에 시나리오의 시트가 더하고(immune) 빼는 것(vulnerable)이다.
  - 시트: 면역과 약함에 같은 성질을 함께 적거나 같은 성질을 두 번 적으면 받지 않는다.
  - 옛 판(형식 60): 부상의 성질과 몬스터의 면역, 약함을 비운다. 옛 룰북: 마이그레이션이 템플릿의 성질을 채운다.
  - 서술: 입은 부상은 몸 상태에 붙고, 면역이라 입지 않은 부상은 결과 줄에 붙는다.
몬스터의 차례에서 부상(기절)이 행동을 막는 것은 test_monster_turns.py 에 있다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError

from app.assets.bestiaries.models import MonsterKind
from app.assets.scenarios.schemas import MonsterSheet
from app.assets.scenarios.snapshot import MonsterSnapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_60
from app.engine.dice import ScriptedDice
from app.engine.ruleset import InjuryNature
from app.engine.templates import SRD5, Template, from_template
from app.rounds.injuries import expire_monsters, immune_to
from app.rounds.move_lines import describe_npc_impact
from app.rounds.narration_request import to_npc_impact
from app.rounds.narrator import NpcImpact
from app.tables.injuries import Moment
from app.tables.models import NpcStatus, TableInjury
from app.tables.monsters import immunities
from tests.narration_model import asset_body
from tests.sheets import SHEET, make_sheet
from tests.test_monster_combat import (
    BESTIARIES_URL,
    LOREBOOKS_URL,
    NO_INJURY,
    PASS,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    TABLES_URL,
    bearer,
    declare,
    events_of,
    load_dice,
    monster_named,
    send,
    strike,
    table_url,
)
from tests.test_ruleset import load_migration

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
MONSTER_SHEET = make_sheet(max_hp=4)

# 부상 표의 눈. SRD5 의 11 은 기절, 17 은 팔 골절이다
STUNNED = 11
BROKEN_ARM = 17
# 쥐의 HP 4 중 1 이 남는 피해. 큰 타격(절반 이상)이다
BIG_HIT = 3

BITE_BACK = '쥐를 걷어찬다.'
WAIT = '숨을 고른다.'


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


async def post(client: AsyncClient, url: str, headers: dict[str, str], **body) -> dict:
    response = await client.post(url, json=asset_body(url, body), headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def start_table(client: AsyncClient, me: dict[str, str], **rat_sheet) -> dict:
    """
    쥐와 해골이 있는 입구에서 테이블을 시작한다. rat_sheet 는 쥐의 시트에 더할 칸이다(immune, vulnerable).

    돌려주는 것은 테이블이다.
    """
    lorebook = await post(client, LOREBOOKS_URL, me, title='지하 수로')
    gate = await post(client, f'{LOREBOOKS_URL}/{lorebook["id"]}/entries', me, name='수로 입구', kind='place')
    bestiary = await post(client, BESTIARIES_URL, me, title='지하 수로의 것들')
    monsters = f'{BESTIARIES_URL}/{bestiary["id"]}/monsters'
    rat = await post(client, monsters, me, name='수로 쥐', kind='beast', content='개만 한 쥐')
    skeleton = await post(client, monsters, me, name='해골 병사', kind='undead', content='녹슨 창을 든 해골')
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    scenario = await post(
        client,
        SCENARIOS_URL,
        me,
        title='지하 수로',
        rulebook_id=rulebook['id'],
        lorebook_ids=[lorebook['id']],
        bestiary_ids=[bestiary['id']],
        openings=['물 떨어지는 소리가 난다.'],
        default_sheet=SHEET,
        monster_sheets=[
            {'monster_id': rat['id'], 'sheet': MONSTER_SHEET, **rat_sheet},
            {'monster_id': skeleton['id'], 'sheet': MONSTER_SHEET},
        ],
        start_place=gate['id'],
        encounters=[
            {'place_id': gate['id'], 'monster_id': rat['id'], 'count': 1},
            {'place_id': gate['id'], 'monster_id': skeleton['id'], 'count': 1},
        ],
    )
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table


def monster_effect(closing: dict) -> dict:
    return closing['declarations'][0]['outcome']['monster_effect']


# --- 라운드 ---


async def test_a_big_hit_can_break_a_monster_s_arm(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table = await start_table(client, me)
    rat = await monster_named(client, me, table, '수로 쥐')
    dice = load_dice(app, [PASS, BIG_HIT, BROKEN_ARM])

    closing = await declare(client, me, table, BITE_BACK, strike(rat['id']))

    injury_roll = monster_effect(closing)['injury_roll']
    assert (injury_roll['trigger'], injury_roll['roll'], injury_roll['injury']) == ('big_hit', BROKEN_ARM, 'broken_arm')
    assert injury_roll['immune'] is None
    assert dice.remaining == 0
    assert (await monster_named(client, me, table, '수로 쥐'))['injuries'] == ['broken_arm']
    # 다른 마리는 멀쩡하다
    assert (await monster_named(client, me, table, '해골 병사'))['injuries'] == []
    (gained,) = await events_of(client, me, table, 'injury_gained')
    payload = gained['payload']
    assert (payload['monster_id'], payload['name'], payload['injury']) == (rat['id'], '수로 쥐', 'broken_arm')
    assert not {'user_id', 'entry_id'} & set(payload)
    (changed,) = await events_of(client, me, table, 'monster_changed')
    assert changed['payload']['injury_roll']['injury'] == 'broken_arm'
    assert gained['caused_by_sequence'] == changed['sequence']


async def test_a_lucky_monster_keeps_no_injury(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table = await start_table(client, me)
    rat = await monster_named(client, me, table, '수로 쥐')
    load_dice(app, [PASS, BIG_HIT, NO_INJURY])

    closing = await declare(client, me, table, BITE_BACK, strike(rat['id']))

    assert monster_effect(closing)['injury_roll']['injury'] is None
    assert (await monster_named(client, me, table, '수로 쥐'))['injuries'] == []
    assert await events_of(client, me, table, 'injury_gained') == []


async def test_a_small_hit_rolls_no_table(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table = await start_table(client, me)
    rat = await monster_named(client, me, table, '수로 쥐')
    # 1 은 HP 4 의 절반이 안 된다. 부상 표의 눈이 없어도 된다
    dice = load_dice(app, [PASS, 1])

    closing = await declare(client, me, table, BITE_BACK, strike(rat['id']))

    assert monster_effect(closing)['injury_roll'] is None
    assert dice.remaining == 0


async def test_an_aimed_hit_takes_the_eye_without_rolling(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table = await start_table(client, me)
    rat = await monster_named(client, me, table, '수로 쥐')
    # 큰 타격이지만 노려 친 타격이라 표를 굴리지 않는다
    dice = load_dice(app, [PASS, BIG_HIT])

    closing = await declare(client, me, table, BITE_BACK, strike(rat['id'], aim='lost_eye'))

    injury_roll = monster_effect(closing)['injury_roll']
    assert (injury_roll['trigger'], injury_roll['roll'], injury_roll['injury']) == ('called_shot', None, 'lost_eye')
    assert dice.remaining == 0
    assert (await monster_named(client, me, table, '수로 쥐'))['injuries'] == ['lost_eye']


async def test_an_injury_the_monster_wears_cannot_be_aimed_at(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    table = await start_table(client, me)
    rat = await monster_named(client, me, table, '수로 쥐')
    load_dice(app, [PASS, 1])
    await declare(client, me, table, BITE_BACK, strike(rat['id'], aim='lost_eye'))
    await narrated()

    again = await send(client, me, table, BITE_BACK, strike(rat['id'], aim='lost_eye'))

    assert again.status_code == status.HTTP_409_CONFLICT
    assert again.json()['reason'] == 'already_injured'


async def test_a_short_injury_ends_on_a_monster(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    table = await start_table(client, me)
    rat = await monster_named(client, me, table, '수로 쥐')
    load_dice(app, [PASS, BIG_HIT, STUNNED])
    await declare(client, me, table, BITE_BACK, strike(rat['id']))
    await narrated()
    assert (await monster_named(client, me, table, '수로 쥐'))['injuries'] == ['stunned']

    # 기절은 한 라운드 간다. 둘째 라운드가 닫히면 풀린다
    load_dice(app, [])
    await declare(client, me, table, WAIT)
    await narrated()

    assert (await monster_named(client, me, table, '수로 쥐'))['injuries'] == []
    (ended,) = await events_of(client, me, table, 'injury_ended')
    assert (ended['payload']['monster_id'], ended['payload']['injury']) == (rat['id'], 'stunned')
    assert ended['payload']['name'] == '수로 쥐'


def monster_state(status_: str = NpcStatus.ALIVE) -> SimpleNamespace:
    """테이블의 마리 하나. 1 라운드에 기절했고 2 라운드가 닫힐 때 풀린다."""
    stunned = TableInjury(injury='stunned', round_number=1, ends_after_round=2)
    return SimpleNamespace(id=uuid.uuid4(), monster_id=uuid.uuid4(), number=1, status=status_, injuries=[stunned])


def test_only_the_scene_s_monsters_are_told_and_the_dead_keep_theirs():
    here, away, dead = monster_state(), monster_state(), monster_state(NpcStatus.DEAD)
    scene = SimpleNamespace(monsters=[SimpleNamespace(state=here, name='수로 쥐')], all_monsters=[here, away, dead])
    moment = Moment(round_number=2, now=0, scene_end=10)

    ended = expire_monsters(scene, SRD5, ScriptedDice([]), uuid.uuid4(), moment, {})

    # 장면의 마리만 알린다(부를 이름이 있다). 다른 곳의 마리도 풀리지만 알리지 않는다
    assert [(one.holder, one.injury.injury) for one in ended] == [
        ({'monster_id': str(here.id), 'name': '수로 쥐'}, 'stunned')
    ]
    assert away.injuries[0].ended_at is not None
    # 죽은 마리의 부상은 그대로 둔다
    assert dead.injuries[0].ended_at is None


# --- 면역 ---


async def test_a_monster_immune_to_the_nature_shrugs_it_off(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table = await start_table(client, me, immune=['stun'])
    rat = await monster_named(client, me, table, '수로 쥐')
    load_dice(app, [PASS, BIG_HIT, STUNNED])

    closing = await declare(client, me, table, BITE_BACK, strike(rat['id']))

    # 굴린 것은 남는다. 나온 기절에 면역이라 입지 않았다
    injury_roll = monster_effect(closing)['injury_roll']
    assert (injury_roll['roll'], injury_roll['injury'], injury_roll['immune']) == (STUNNED, None, 'stunned')
    assert (await monster_named(client, me, table, '수로 쥐'))['injuries'] == []
    assert await events_of(client, me, table, 'injury_gained') == []


async def test_an_immune_monster_cannot_be_aimed_at(client: AsyncClient, me: dict[str, str]):
    table = await start_table(client, me, immune=['body'])
    rat = await monster_named(client, me, table, '수로 쥐')

    response = await send(client, me, table, BITE_BACK, strike(rat['id'], aim='lost_eye'))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'target_immune'


async def test_the_sheet_s_lists_are_in_the_version(client: AsyncClient, me: dict[str, str]):
    table = await start_table(client, me, immune=['stun'], vulnerable=['poison'])
    rat = await monster_named(client, me, table, '수로 쥐')

    # 판에 굳어 그 판의 면역으로 쓴다. 장면에는 면역을 싣지 않는다
    assert 'immune' not in rat
    response = await send(client, me, table, BITE_BACK, strike(rat['id'], aim='lost_eye'))
    assert response.status_code == status.HTTP_200_OK, response.text


def snapshot_of(kind: MonsterKind, immune: list[str] | None = None, vulnerable: list[str] | None = None):
    return MonsterSnapshot(
        id=uuid.uuid4(),
        name='것',
        content='',
        kind=kind,
        sheet=MONSTER_SHEET,
        immune=immune or [],
        vulnerable=vulnerable or [],
    )


@pytest.mark.parametrize(
    ('kind', 'immune', 'vulnerable', 'expected'),
    [
        (MonsterKind.BEAST, [], [], set()),
        # 언데드는 독, 구조물은 독과 정신에 면역이다(타입의 성질표)
        (MonsterKind.UNDEAD, [], [], {InjuryNature.POISON}),
        (MonsterKind.CONSTRUCT, [], [], {InjuryNature.POISON, InjuryNature.MIND}),
        # 시트가 더하고 뺀다
        (MonsterKind.BEAST, ['stun'], [], {InjuryNature.STUN}),
        (MonsterKind.UNDEAD, [], ['poison'], set()),
        (MonsterKind.CONSTRUCT, ['sense'], ['mind'], {InjuryNature.POISON, InjuryNature.SENSE}),
    ],
)
def test_immunities_are_the_kind_s_plus_the_sheet_s(kind, immune, vulnerable, expected):
    assert immunities(snapshot_of(kind, immune, vulnerable)) == expected


def test_an_injury_without_natures_is_taken_by_anyone():
    rules = SRD5.model_copy(
        update={'injuries': tuple(injury.model_copy(update={'natures': ()}) for injury in SRD5.injuries)}
    )
    everything = frozenset(InjuryNature)

    assert immune_to(SRD5, 'poisoned', everything)
    assert not immune_to(rules, 'poisoned', everything)
    # 규칙에 없는 부상은 면역이 아니다
    assert not immune_to(SRD5, 'nose', everything)


# --- 시트 ---


@pytest.mark.parametrize(
    'fields',
    [
        {'immune': ['poison'], 'vulnerable': ['poison']},
        {'immune': ['poison', 'poison']},
        {'vulnerable': ['mind', 'mind']},
        {'immune': ['fire']},
    ],
)
def test_a_sheet_with_confused_natures_is_refused(fields: dict):
    with pytest.raises(ValidationError):
        MonsterSheet.model_validate({'monster_id': str(uuid.uuid4()), 'sheet': MONSTER_SHEET, **fields})


def test_injury_natures_cannot_repeat():
    injuries = SRD5.model_dump(mode='json')['injuries']
    repeated = [{**injuries[0], 'natures': ['stun', 'stun']}, *injuries[1:]]

    with pytest.raises(ValidationError):
        type(SRD5).model_validate({**SRD5.model_dump(mode='json'), 'injuries': repeated})


# --- 옛 판과 옛 룰북 ---


def test_an_old_version_has_no_natures_and_no_immunities():
    rules = SRD5.model_dump(mode='json')
    old = {
        'format': 60,
        'rulebook': {'rules': {**rules, 'injuries': [{'key': 'stunned'}]}},
        'monsters': [{'id': 'm'}],
    }

    upgraded = upgrade_from_60(old)

    assert upgraded['format'] == 61
    assert upgraded['rulebook']['rules']['injuries'] == [{'key': 'stunned', 'natures': []}]
    assert upgraded['monsters'] == [{'id': 'm', 'immune': [], 'vulnerable': []}]
    # 받은 문서는 그대로다
    assert old['monsters'] == [{'id': 'm'}]
    assert UPGRADES[60] is upgrade_from_60


def test_the_migration_fills_the_template_s_natures_and_takes_them_back():
    migration = load_migration('injured_monsters')
    injuries = [{'key': 'stunned'}, {'key': 'nose'}, {'key': 'poisoned', 'natures': ['body']}]
    old = {'template': 'srd5', 'injuries': injuries}

    filled = migration.with_natures(old)

    # 템플릿의 같은 이름표면 그 성질, 템플릿에 없는 부상은 빈 성질, 이미 있으면 그대로다
    assert filled['injuries'] == [
        {'key': 'stunned', 'natures': ['stun']},
        {'key': 'nose', 'natures': []},
        {'key': 'poisoned', 'natures': ['body']},
    ]
    assert migration.with_natures(filled) == filled
    assert migration.without_natures(filled) == {
        'template': 'srd5',
        'injuries': [{'key': key} for key in ('stunned', 'nose', 'poisoned')],
    }
    # 템플릿을 모르는 규칙은 모두 빈 성질이다
    assert migration.with_natures({'injuries': [{'key': 'stunned'}]})['injuries'] == [{'key': 'stunned', 'natures': []}]


@pytest.mark.parametrize('template', [Template.SRD5, Template.HORROR])
def test_the_migration_knows_the_template_s_natures(template: Template):
    # 마이그레이션은 앱의 코드를 가져오지 않는다. 템플릿을 고치면 이 테스트가 깨진다
    migration = load_migration('injured_monsters')
    rules = from_template(template)
    natures = {injury.key: [nature.value for nature in injury.natures] for injury in rules.injuries}

    assert migration.TEMPLATE_NATURES[template] == natures


# --- 서술 ---


def test_a_resisted_injury_is_not_told_as_a_new_one():
    roll = {'trigger': 'big_hit', 'roll': STUNNED, 'injury': None, 'name': '기절', 'immune': 'stunned'}
    effect = {'kind': 'damage', 'name': '해골 병사', 'amount': 3, 'condition': '크게 다침', 'injury_roll': roll}

    impact = to_npc_impact(effect)

    assert (impact.injury, impact.resisted) == (None, '기절')
    taken = {**roll, 'injury': 'stunned', 'immune': None}
    assert (
        to_npc_impact({**effect, 'injury_roll': taken}).injury,
        to_npc_impact({**effect, 'injury_roll': taken}).resisted,
    ) == ('기절', None)


def test_the_narrator_hears_what_the_monster_shrugged_off():
    impact = NpcImpact(kind='damage', name='해골 병사', amount=3, condition='크게 다침', resisted='중독')

    assert describe_npc_impact(impact) == '→ 해골 병사 피해 3 (크게 다침). 중독에 면역이라 멀쩡하다'


def test_the_narrator_hears_the_new_injury():
    impact = NpcImpact(kind='damage', name='수로 쥐', amount=3, condition='크게 다침', injury='팔 골절')

    assert describe_npc_impact(impact) == '→ 수로 쥐 피해 3 (크게 다침). 새 부상: 팔 골절'
