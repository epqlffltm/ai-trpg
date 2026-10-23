# trpg-server/tests/test_injury_minutes.py

"""
오래 가는 부상과 치료의 기간을 게임 안의 시간(분)으로 적는 규칙(판 형식 25, 달력 2단계의 둘째)을 검증한다.

셋을 본다.
  - 규칙의 모양: 짧은 것은 라운드 수(rounds), 오래 가는 것은 낫기까지의 분(heal_minutes)과 치료가 앞당기는 분
    (treat_minutes), 치료 실패 표의 덧남은 늦춰지는 분(delay_minutes)이다. 섞어 적으면 받지 않는다.
  - 옛 판(형식 24): SRD5 에서 온 규칙은 지금의 SRD5 값(팔 골절 14일 …)으로 읽고,
    다른 규칙은 라운드 수에 그 판의 기본 걸음을 곱해 읽는다.
  - DB 의 룰북: 마이그레이션이 같은 값을 채운다. 두 번 돌려도 같고, 되돌리면 옛 라운드 수로 돌아온다.
"""

import copy
import json

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_24
from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5
from tests.signing import SigningKey
from tests.test_injuries import make_format_13
from tests.test_npc_actions import bearer, start_table
from tests.test_ruleset import load_migration
from tests.test_treatment import ME

pytestmark = pytest.mark.usefixtures('clean_tables')

# 하루(분). 템플릿의 부상과 치료의 기간을 적는 단위다
DAY = 24 * 60


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """테이블을 여는 사람의 머리말. 룰북을 하나 만든다."""
    return bearer(signing_key, ME)


def old_srd5_rules() -> dict:
    """형식 25 전의 SRD5 규칙. 오래 가는 부상과 치료가 라운드 수다. 그때의 마이그레이션들이 채운 값이다."""
    rules = SRD5.model_dump(mode='json')
    injuries = load_migration('injuries').INJURY_RULES
    treatment = load_migration('treatment')
    treated = [
        {**injury, **treatment.TREATABLE.get(injury['key'], treatment.UNTREATABLE)} for injury in injuries['injuries']
    ]
    return {**rules, **injuries, 'injuries': treated, 'treatment': copy.deepcopy(treatment.TREATMENT)}


def make_format_24(rules: dict, round_minutes: int = 10) -> dict:
    """형식 24 의 판. 규칙과 판의 기본 걸음을 정한다."""
    document = make_format_13()
    while document['format'] < 24:
        document = UPGRADES[document['format']](document)
    clock = {**document['clock'], 'round_minutes': round_minutes}
    return {**document, 'clock': clock, 'rulebook': {**document['rulebook'], 'rules': rules}}


def srd5_injuries_with(key: str, **fields) -> list[dict]:
    """지금의 SRD5 부상 목록에서 하나의 칸만 바꾼 것."""
    return [
        {**injury, **fields} if injury['key'] == key else injury for injury in SRD5.model_dump(mode='json')['injuries']
    ]


# --- 규칙의 모양 ---


def test_the_template_heals_lasting_injuries_in_days():
    lasting = {injury.key: (injury.rounds, injury.heal_minutes, injury.treat_minutes) for injury in SRD5.injuries}

    assert lasting['broken_arm'] == (None, 14 * DAY, 3 * DAY)
    assert lasting['leg_wound'] == (None, 7 * DAY, 2 * DAY)
    # 짧은 것은 라운드 수 그대로다
    assert lasting['stunned'] == (1, None, None)
    assert lasting['lost_eye'] == (None, None, None)
    delays = [row.delay_minutes for row in SRD5.treatment.mishaps.rows]
    assert delays == [None, 2 * DAY, DAY, None, None]


@pytest.mark.parametrize(
    'injuries',
    [
        # 오래 가는 것에 라운드 수를 적거나, 낫기까지의 시간을 빠뜨린다
        srd5_injuries_with('broken_arm', rounds=30),
        srd5_injuries_with('broken_arm', heal_minutes=None),
        # 짧은 것과 결손에 낫기까지의 시간을 적는다
        srd5_injuries_with('stunned', heal_minutes=60),
        srd5_injuries_with('lost_eye', heal_minutes=60),
        # 옛 칸은 받지 않는다
        srd5_injuries_with('broken_arm', treat_rounds=10),
        # 한 해보다 길다
        srd5_injuries_with('broken_arm', heal_minutes=366 * DAY),
    ],
)
def test_rejects_mixed_up_durations(injuries: list[dict]):
    with pytest.raises(ValidationError):
        Ruleset.model_validate({**SRD5.model_dump(mode='json'), 'injuries': injuries})


# --- 옛 판 ---


def test_an_old_srd5_version_is_read_with_the_template_days():
    old = make_format_24(old_srd5_rules())

    current = read_snapshot(old)

    assert current.rulebook.rules.injuries == SRD5.injuries
    assert current.rulebook.rules.treatment == SRD5.treatment
    assert UPGRADES[24] is upgrade_from_24


def test_rules_not_from_the_template_are_read_with_the_steps_of_the_version():
    rules = {**old_srd5_rules(), 'template': 'homebrew'}

    # 라운드 하나에 한 시간이 흐르는 판
    upgraded = upgrade_from_24(make_format_24(rules, round_minutes=60))

    injuries = {injury['key']: injury for injury in upgraded['rulebook']['rules']['injuries']}
    arm = injuries['broken_arm']
    assert (arm.get('rounds'), arm['heal_minutes'], arm['treat_minutes']) == (None, 30 * 60, 10 * 60)
    assert 'treat_rounds' not in arm
    assert injuries['stunned']['rounds'] == 1
    rows = upgraded['rulebook']['rules']['treatment']['mishaps']['rows']
    assert [row['delay_minutes'] for row in rows] == [None, 10 * 60, 5 * 60, None, None]
    assert upgraded['format'] == 25


def test_upgrading_does_not_touch_the_document_it_got():
    old = make_format_24(old_srd5_rules())
    before = copy.deepcopy(old)

    upgrade_from_24(old)

    assert old == before


# --- DB 의 룰북 ---


async def rewrite(session: AsyncSession, migration, injury_step, row_step) -> None:
    """마이그레이션의 룰북 고치기를 지금 세션에서 돌린다."""
    await session.run_sync(lambda sync: migration.rewrite_rulebooks(sync.connection(), injury_step, row_step))
    await session.commit()


async def test_the_migration_moves_old_rulebooks_to_minutes_and_back(
    client: AsyncClient, me: dict, session: AsyncSession
):
    migration = load_migration('injury_minutes')
    await start_table(client, me)
    old = old_srd5_rules()
    await session.execute(text('UPDATE rulebooks SET rules = CAST(:rules AS JSONB)'), {'rules': json.dumps(old)})
    await session.commit()

    # 두 번 돌려도 같다
    for _ in range(2):
        await rewrite(session, migration, migration.injury_to_minutes, migration.row_to_minutes)
    upgraded = await session.scalar(text('SELECT rules FROM rulebooks'))
    await rewrite(session, migration, migration.injury_to_rounds, migration.row_to_rounds)
    downgraded = await session.scalar(text('SELECT rules FROM rulebooks'))

    assert upgraded == SRD5.model_dump(mode='json')
    assert downgraded == old
