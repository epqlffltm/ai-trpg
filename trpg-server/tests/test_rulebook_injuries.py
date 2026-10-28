# trpg-server/tests/test_rulebook_injuries.py

"""
룰북의 부상과 부상 표와 굴리는 때를 제작자가 고치는 것(#886 ②-a, app/assets/rulebooks/service.py)을 검증한다.

전에는 룰북의 부상이 템플릿 그대로였다. 이제 만들 때와 고칠 때 injuries, injury_table, injury_triggers 를 보낸다.
칸끼리 가리키는 것(부상의 성질, 부상 표의 줄, 노려 치기, 치료, 수치의 문턱, 기술)은 규칙 한 벌로 다시 읽어 본다.
틀리면 422 이고, 성질 → 부상 → 부상 표 → 굴리는 때 → 면역 → 수치 → 기술의 차례로 처음 틀린 칸을 field 로 알려 준다.
룰북은 SRD5 에서 만든다. 부상 표는 이십면체이고 11~12 가 기절, 13 이 실명이다.
"""

import copy

import pytest
from fastapi import status
from httpx import AsyncClient

from app.assets.scenarios.upgrades import CLASSIC_NATURES
from app.engine.templates import SRD5
from tests import test_monster_injuries as injuries

pytestmark = pytest.mark.usefixtures('clean_tables')

me = injuries.me
RULEBOOKS_URL = injuries.RULEBOOKS_URL
FIRE = {'key': 'fire', 'name': '화염', 'category': '원소'}
BURNED = {
    'key': 'burned',
    'name': '화상',
    'fact': '살갗이 데어 쓰라리다.',
    'effects': [{'kind': 'penalty', 'abilities': ['dex'], 'amount': 1}],
    'healing': 'rounds',
    'rounds': 3,
    'natures': ['fire'],
}
TEMPLATE = SRD5.model_dump(mode='json')
OFF = {'big_hit_percent': None, 'downed': False, 'called_shot': False}


async def patch(client: AsyncClient, rulebook: dict, headers: dict, **body):
    return await client.patch(f'{RULEBOOKS_URL}/{rulebook["id"]}', json=body, headers=headers)


def without(key: str) -> tuple[list, dict]:
    """그 부상을 뺀 부상들과, 그 부상의 줄을 '부상 없음'으로 바꾼 부상 표."""
    kept = [injury for injury in TEMPLATE['injuries'] if injury['key'] != key]
    table = copy.deepcopy(TEMPLATE['injury_table'])
    for row in table['rows']:
        if row['injury'] == key:
            row['injury'] = None
    return kept, table


async def test_a_rulebook_may_start_with_its_own_injuries(client: AsyncClient, me: dict):
    rulebook = await injuries.post(
        client,
        RULEBOOKS_URL,
        me,
        title='불의 룰북',
        natures=[*CLASSIC_NATURES, FIRE],
        injuries=[*TEMPLATE['injuries'], BURNED],
    )

    assert rulebook['rules']['injuries'][-1]['key'] == 'burned'
    assert rulebook['rules']['injury_table'] == TEMPLATE['injury_table']


async def test_a_new_injury_needs_its_nature(client: AsyncClient, me: dict):
    rulebook = await injuries.post(client, RULEBOOKS_URL, me, title='룰북')

    missing = await patch(client, rulebook, me, injuries=[*TEMPLATE['injuries'], BURNED])
    added = await patch(
        client, rulebook, me, natures=[*CLASSIC_NATURES, FIRE], injuries=[*TEMPLATE['injuries'], BURNED]
    )

    assert (missing.status_code, missing.json()['field']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'injuries')
    assert added.status_code == status.HTTP_200_OK, added.text
    assert added.json()['rules']['injuries'][-1]['name'] == '화상'


async def test_an_injury_on_the_table_goes_with_its_row(client: AsyncClient, me: dict):
    rulebook = await injuries.post(client, RULEBOOKS_URL, me, title='룰북')
    kept, table = without('blinded')

    alone = await patch(client, rulebook, me, injuries=kept)
    together = await patch(client, rulebook, me, injuries=kept, injury_table=table)

    # 부상 표의 13 이 지운 실명을 가리킨다. 부상만 보내면 부상이 틀린 칸이다
    assert (alone.status_code, alone.json()['field']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'injuries')
    assert together.status_code == status.HTTP_200_OK, together.text
    assert 'blinded' not in [injury['key'] for injury in together.json()['rules']['injuries']]


async def test_the_table_is_cleared_with_null_only_when_nothing_rolls_it(client: AsyncClient, me: dict):
    rulebook = await injuries.post(client, RULEBOOKS_URL, me, title='룰북')

    still_rolled = await patch(client, rulebook, me, injury_table=None)
    turned_off = await patch(client, rulebook, me, injury_table=None, injury_triggers=OFF)
    not_sent = await patch(client, rulebook, me, title='새 이름')

    assert (still_rolled.status_code, still_rolled.json()['field']) == (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        'injury_table',
    )
    assert turned_off.status_code == status.HTTP_200_OK, turned_off.text
    assert (turned_off.json()['rules']['injury_table'], turned_off.json()['rules']['injury_triggers']) == (None, OFF)
    # 보내지 않은 칸은 그대로다
    assert not_sent.json()['rules']['injury_table'] is None


async def test_a_wrong_injury_is_refused_by_its_shape(client: AsyncClient, me: dict):
    rulebook = await injuries.post(client, RULEBOOKS_URL, me, title='룰북')

    response = await patch(client, rulebook, me, injuries=[{**BURNED, 'healing': 'never'}])

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_when_both_are_wrong_the_injuries_are_named_first(client: AsyncClient, me: dict):
    rulebook = await injuries.post(client, RULEBOOKS_URL, me, title='룰북')
    table = copy.deepcopy(TEMPLATE['injury_table'])
    table['rows'][0]['injury'] = 'burned'

    # 화상의 성질(화염)이 규칙에 없고, 부상 표는 그 화상을 가리킨다. 앞의 칸(부상)을 알려 준다
    response = await patch(client, rulebook, me, injuries=[*TEMPLATE['injuries'], BURNED], injury_table=table)

    assert (response.status_code, response.json()['field']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'injuries')
