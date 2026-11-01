# trpg-server/tests/test_growth.py

"""
캐릭터의 성장(#286 ①, app/tables/growth.py)을 검증한다. 룰북의 레벨표와 퀘스트의 경험치의 보상이다.

맵과 픽스처는 tests/test_happenings.py 의 것이다. 방장(기사)과 함께 앉는 사람(약사), 성문(시작)-광장 큰길.
퀘스트는 왕녀 구출 하나다. 진행 중으로 시작하고 광장에 닿으면 이룬다. 시험마다 경험치를 달리 준다.
레벨표(GROWTH)는 레벨 2 가 100, 레벨 3 이 300, 레벨 4 가 600 이다. 오를 때마다 최대 HP +3, 능력치 점수 1(레벨 4 는 2).

보는 것.
  - 룰북: 레벨표를 적고 고치고 지운다(null). 경험치가 줄마다 커지지 않으면 422 다. 템플릿 light 에는 예시가 있다.
  - 게시: 경험치를 주는 퀘스트가 있는데 룰북에 성장이 없으면 409 progression_missing 이다. 판도 거부한다.
  - 라운드: 퀘스트를 이루면 살아 있는 캐릭터마다 경험치를 받는다(quest_changed 의 rewards[].xp).
    레벨표의 줄에 닿으면 오른다. 한 번에 여러 레벨도 오른다. 오른 캐릭터마다 character_leveled 가 잇는다.
    시트에 경험치, 레벨, 다음 레벨의 경험치, 쌓인 능력치 점수가 보이고 최대 HP 와 지금 HP 가 오른다.
  - 순수 함수: 레벨, 다음 레벨, 쓰러진 캐릭터는 최대 HP 만, 상한(경험치, 최대 HP), 마지막 레벨, 성장이 없는 규칙.
  - 옛 판(형식 67)은 성장이 없는 규칙으로 읽는다. 마이그레이션은 두 번 돌려도 같다.
"""

import importlib.util
import uuid
from pathlib import Path

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import Snapshot, read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_67
from app.engine.ruleset import PROGRESSION_MAX_XP, Progression
from app.engine.sheet import SHEET_MAX_HP
from app.tables import growth
from app.tables.models import TableSheet
from app.transcripts.markdown import render_event
from tests import test_happenings as happening_tests
from tests.sheets import SHEET
from tests.test_happenings import reach
from tests.test_map_actions import declare, going, play
from tests.test_table_items import (
    FRIEND,
    ME,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    TABLES_URL,
    events_of,
    kill,
    post,
    read_table,
    table_url,
)
from tests.test_table_map import the_map
from tests.test_transcript_markdown import LABELS, event

pytestmark = pytest.mark.usefixtures('clean_tables')

me = happening_tests.me
friend = happening_tests.friend
lore = happening_tests.lore
more = happening_tests.more

GROWTH = {
    'levels': [
        {'xp': 100, 'max_hp': 3, 'points': 1},
        {'xp': 300, 'max_hp': 3, 'points': 1},
        {'xp': 600, 'max_hp': 3, 'points': 2},
    ]
}


def rescue(more: dict, xp: int) -> dict:
    """진행 중으로 시작하고 광장에 닿으면 이루는 왕녀 구출. 이루면 살아 있는 캐릭터마다 경험치 xp 를 받는다."""
    return {'entry_id': more['rescue']['id'], 'start': 'active', 'conditions': [reach(more['square'])], 'reward_xp': xp}


async def draft_growing(client: AsyncClient, me: dict, more: dict, progression: dict | None, xp: int) -> dict:
    """그 레벨표의 룰북과 경험치를 주는 퀘스트의 시나리오. 게시하지 않았다."""
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북', progression=progression)
    body = {
        'title': '성의 모험',
        'rulebook_id': rulebook['id'],
        'openings': ['성문 앞이다.'],
        'default_sheet': SHEET,
        'lorebook_ids': [more['lorebook']['id']],
        'quests': [rescue(more, xp)],
        **the_map(more),
    }
    return await post(client, SCENARIOS_URL, me, **body)


async def start_growing(client: AsyncClient, me: dict, friend: dict, more: dict, xp: int) -> dict:
    """GROWTH 의 룰북으로 둘이 앉아 시작한 테이블. 왕녀 구출이 경험치 xp 를 준다."""
    scenario = await draft_growing(client, me, more, GROWTH, xp)
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=2)
    joined = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    assert joined.status_code == status.HTTP_200_OK, joined.text
    await client.put(table_url(table, '/character'), json={'name': '기사'}, headers=me)
    await client.put(table_url(table, '/character'), json={'name': '약사'}, headers=friend)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


def sheet_of(table: dict, user_id: uuid.UUID) -> dict:
    return next(member['sheet'] for member in table['members'] if member['user_id'] == str(user_id))


# --- 룰북 ---


async def test_a_rulebook_keeps_its_level_table(client: AsyncClient, me: dict):
    made = await post(client, RULEBOOKS_URL, me, title='룰북', progression=GROWTH)
    url = f'{RULEBOOKS_URL}/{made["id"]}'

    cleared = await client.patch(url, json={'progression': None}, headers=me)
    untouched = await client.patch(url, json={'title': '바꾼 제목'}, headers=me)
    again = await client.patch(url, json={'progression': {'levels': [{'xp': 50}]}}, headers=me)

    assert made['rules']['progression'] == GROWTH
    assert cleared.json()['rules']['progression'] is None
    assert untouched.json()['rules']['progression'] is None
    assert again.json()['rules']['progression'] == {'levels': [{'xp': 50, 'max_hp': 0, 'points': 0}]}


@pytest.mark.parametrize(
    'levels',
    [
        [{'xp': 100}, {'xp': 100}],
        [{'xp': 300}, {'xp': 100}],
        [],
        [{'xp': 0}],
        [{'xp': 10, 'max_hp': 100}],
        [{'xp': 10, 'points': 11}],
        [{'xp': n + 1} for n in range(20)],
    ],
)
async def test_a_misshaped_level_table_is_refused(client: AsyncClient, me: dict, levels: list):
    made = await post(client, RULEBOOKS_URL, me, title='룰북')

    response = await client.patch(f'{RULEBOOKS_URL}/{made["id"]}', json={'progression': {'levels': levels}}, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text


async def test_the_light_template_grows_and_the_others_do_not(client: AsyncClient, me: dict):
    light = await post(client, RULEBOOKS_URL, me, title='가벼운', template='light')
    srd5 = await post(client, RULEBOOKS_URL, me, title='기본', template='srd5')

    assert len(light['rules']['progression']['levels']) == 4
    assert srd5['rules']['progression'] is None


# --- 게시 ---


async def test_experience_needs_a_level_table(client: AsyncClient, me: dict, more: dict):
    flat = await draft_growing(client, me, more, None, 50)
    growing = await draft_growing(client, me, more, GROWTH, 50)

    refused = await client.post(f'{SCENARIOS_URL}/{flat["id"]}/versions', json={}, headers=me)
    published = await client.post(f'{SCENARIOS_URL}/{growing["id"]}/versions', json={}, headers=me)

    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['problems'] == ['progression_missing']
    assert published.status_code == status.HTTP_201_CREATED, published.text
    assert read_snapshot(published.json()['snapshot']).quests[0].reward_xp == 50
    document = published.json()['snapshot']
    flat_rules = {**document['rulebook']['rules'], 'progression': None}
    with pytest.raises(ValidationError):
        Snapshot.model_validate({**document, 'rulebook': {**document['rulebook'], 'rules': flat_rules}})


# --- 라운드 ---


async def test_a_quest_gives_experience_and_raises_the_level(
    client: AsyncClient, me: dict, friend: dict, more: dict, narrated
):
    table = await start_growing(client, me, friend, more, 150)

    await play(client, me, friend, table, narrated, mine=going(more['square']))
    after = await read_table(client, me, table)

    (changed,) = await events_of(client, me, table, 'quest_changed')
    gained = {reward['character_name']: reward['xp'] for reward in changed['payload']['rewards']}
    assert gained['기사'] == {
        'count': 150,
        'total': 150,
        'capped': False,
        'previous_level': 1,
        'level': 2,
        'max_hp': 13,
        'points': 1,
    }
    assert gained['약사']['level'] == 2
    for user_id in (ME, FRIEND):
        sheet = sheet_of(after, user_id)
        assert (sheet['xp'], sheet['level'], sheet['next_level_xp'], sheet['points']) == (150, 2, 300, 1)
        assert (sheet['max_hp'], sheet['hp']) == (13, 13)
    leveled = await events_of(client, me, table, 'character_leveled')
    assert [one['payload']['character_name'] for one in leveled] == ['기사', '약사']
    assert leveled[0]['payload'] == {
        'user_id': str(ME),
        'character_name': '기사',
        'previous_level': 1,
        'level': 2,
        'xp': 150,
        'max_hp': 13,
        'points': 1,
    }
    assert leveled[0]['actor_id'] is None
    assert leveled[0]['sequence'] > changed['sequence']
    assert leveled[0]['action_group_id'] == changed['action_group_id']


async def test_much_experience_raises_several_levels_at_once(
    client: AsyncClient, me: dict, friend: dict, more: dict, narrated
):
    table = await start_growing(client, me, friend, more, 700)

    await play(client, me, friend, table, narrated, mine=going(more['square']))

    sheet = sheet_of(await read_table(client, me, table), ME)
    # 레벨 2, 3, 4 를 한꺼번에 오른다. 최대 HP 는 셋 더한 만큼, 점수는 1 + 1 + 2. 마지막 레벨이라 다음이 없다
    assert (sheet['level'], sheet['max_hp'], sheet['points'], sheet['next_level_xp']) == (4, 19, 4, None)
    (first, _) = await events_of(client, me, table, 'character_leveled')
    assert (first['payload']['previous_level'], first['payload']['level']) == (1, 4)


async def test_too_little_experience_raises_no_level(client: AsyncClient, me: dict, friend: dict, more: dict, narrated):
    table = await start_growing(client, me, friend, more, 40)

    await play(client, me, friend, table, narrated, mine=going(more['square']))

    sheet = sheet_of(await read_table(client, me, table), ME)
    assert (sheet['xp'], sheet['level'], sheet['next_level_xp'], sheet['max_hp']) == (40, 1, 100, 10)
    assert await events_of(client, me, table, 'character_leveled') == []


async def test_the_dead_get_no_experience(
    client: AsyncClient, me: dict, friend: dict, more: dict, session: AsyncSession, narrated
):
    table = await start_growing(client, me, friend, more, 150)
    await kill(session, FRIEND)
    await session.commit()

    # 죽은 사람은 선언하지 않는다. 산 사람의 선언으로 닫힌다
    declared = await declare(client, me, table, going(more['square']))
    assert declared.status_code == status.HTTP_200_OK, declared.text
    await narrated()

    (changed,) = await events_of(client, me, table, 'quest_changed')
    assert [reward['character_name'] for reward in changed['payload']['rewards']] == ['기사']
    xp = await session.scalar(text('SELECT xp FROM table_sheets WHERE user_id = :user_id'), {'user_id': FRIEND})
    assert xp == 0


async def test_a_table_without_growth_shows_level_one(client: AsyncClient, me: dict, friend: dict, more: dict):
    table = await happening_tests.start(client, me, friend, more, [])

    sheet = sheet_of(await read_table(client, me, table), ME)

    assert (sheet['xp'], sheet['level'], sheet['next_level_xp'], sheet['points']) == (0, 1, None, 0)


def test_the_transcript_names_the_level():
    payload = {'character_name': '기사', 'previous_level': 2, 'level': 3, 'xp': 320, 'max_hp': 14, 'points': 1}

    assert '레벨: 기사 · 2 → 3 (최대 HP 14, 능력치 점수 1)' in render_event(event('character_leveled', payload), LABELS)


# --- 순수 함수 ---

PROGRESSION = Progression.model_validate(GROWTH)


def sheet(xp: int = 0, hp: int = 10, max_hp: int = 10, points: int = 0) -> TableSheet:
    return TableSheet(xp=xp, hp=hp, max_hp=max_hp, points=points)


def test_the_level_follows_the_experience():
    assert [growth.level_of(xp, PROGRESSION) for xp in (0, 99, 100, 299, 300, 600, 10_000)] == [1, 1, 2, 2, 3, 4, 4]
    assert [growth.next_level_xp(xp, PROGRESSION) for xp in (0, 100, 599, 600)] == [100, 300, 600, None]
    assert (growth.level_of(5_000, None), growth.next_level_xp(0, None)) == (1, None)


def test_a_downed_character_gains_only_the_maximum():
    downed = sheet(hp=0)

    growth.gain(downed, 100, PROGRESSION)

    assert (downed.hp, downed.max_hp, downed.points) == (0, 13, 1)


def test_the_caps_hold():
    near = sheet(xp=PROGRESSION_MAX_XP - 10, max_hp=SHEET_MAX_HP - 1, hp=SHEET_MAX_HP - 1)

    gained = growth.gain(near, 50, PROGRESSION)

    assert (gained['count'], gained['capped'], near.xp) == (10, True, PROGRESSION_MAX_XP)
    # 이미 마지막 레벨이라 최대 HP 는 오르지 않는다
    assert (gained['previous_level'], gained['level'], near.max_hp) == (4, 4, SHEET_MAX_HP - 1)
    climbing = sheet(max_hp=SHEET_MAX_HP - 1, hp=5)
    growth.gain(climbing, 100, PROGRESSION)
    assert (climbing.max_hp, climbing.hp) == (SHEET_MAX_HP, 6)


def test_no_growth_or_no_experience_changes_nothing():
    plain = sheet()

    assert growth.gain(plain, 100, None) is None
    assert growth.gain(plain, 0, PROGRESSION) is None
    assert (plain.xp, plain.max_hp, plain.points) == (0, 10, 0)
    assert not growth.leveled(None)


# --- 옛 판과 마이그레이션 ---


def test_an_old_snapshot_reads_as_no_growth():
    upgraded = upgrade_from_67({'format': 67, 'rulebook': {'rules': {'die': 20}}})

    assert upgraded == {'format': 68, 'rulebook': {'rules': {'die': 20, 'progression': None}}}
    assert UPGRADES[67] is upgrade_from_67


def load_migration():
    path = next(Path('migrations/versions').glob('*_progression.py'))
    spec = importlib.util.spec_from_file_location('progression_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_fills_no_growth_once_and_undoes():
    migration = load_migration()
    old = {'die': 20}

    filled = migration.with_progression(old)

    assert filled == {'die': 20, 'progression': None}
    assert migration.with_progression({'die': 20, 'progression': GROWTH}) == {'die': 20, 'progression': GROWTH}
    assert migration.with_progression(filled) == filled
    assert migration.without_progression(filled) == old
    assert migration.quest_without_xp({'entry_id': 'x', 'reward_xp': 5}) == {'entry_id': 'x'}
