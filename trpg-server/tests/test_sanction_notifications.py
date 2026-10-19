# trpg-server/tests/test_sanction_notifications.py

"""
운영자의 제재를 당사자의 알림함에 알리는 것(app/operators/notices.py)을 검증한다.

보는 것.
  - 시나리오 제재는 제작자에게 한 줄. 이번 제재로 저절로 공개가 금지되면 그 알림이 하나 더 간다(이미 금지 중이면 없다).
  - 운영자의 공개 금지와 풀기는 그 사람에게 한 줄씩. 다시 금지해도 알림의 열쇠가 다르다.
  - 사유와 운영자는 알림에 싣지 않는다.
  - 제재가 되지 않았으면(409, 404) 알림도 없다. 테이블 끝내기는 알리지 않는다.
알림 서버에 보내는 것은 tests/test_notifications.py 가 본다. 여기서는 발송함에 적힌 것만 본다.
"""

import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import OutgoingNotification
from app.operators.models import OperatorAction
from app.operators.notices import action_key
from tests.signing import SigningKey
from tests.test_listings_api import ME, TITLE, make_public
from tests.test_operator_sanctions import (
    ADMIN_URL,
    OPERATOR,
    REASON,
    ban,
    bearer,
    open_table,
    ready_to_publish,
    sanction,
    sanction_many,
)

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """시나리오를 쓰고 공개하는 제작자의 머리말."""
    return bearer(signing_key, ME)


@pytest.fixture
def operator(signing_key: SigningKey) -> dict[str, str]:
    """운영자의 머리말."""
    return bearer(signing_key, OPERATOR, roles=['operator'])


async def outgoing(session: AsyncSession) -> list[OutgoingNotification]:
    """발송함의 모든 줄. 적은 차례다."""
    session.expire_all()
    return list(await session.scalars(select(OutgoingNotification).order_by(OutgoingNotification.id)))


async def action_ids(session: AsyncSession) -> list[int]:
    """감사 기록의 번호들. 적은 차례다."""
    return list(await session.scalars(select(OperatorAction.id).order_by(OperatorAction.id)))


async def test_a_sanction_is_told_to_the_creator(client: AsyncClient, me: dict, operator: dict, session: AsyncSession):
    scenario = await make_public(client, me)

    await sanction(client, operator, scenario)
    (notice,) = await outgoing(session)
    (action_id,) = await action_ids(session)

    assert (notice.user_id, notice.kind) == (ME, 'scenario.sanctioned')
    assert notice.payload == {
        'scenario_id': scenario['id'],
        'title': TITLE,
        'version_number': 1,
        'publishing_banned': False,
    }
    assert notice.source_key == f'scenario.sanctioned:{action_id}'


async def test_reaching_the_threshold_also_tells_the_ban(
    app: FastAPI, client: AsyncClient, me: dict, operator: dict, session: AsyncSession
):
    app.state.settings.publishing_ban_threshold = 2

    # 셋을 먼저 공개해 둔다. 금지된 뒤에는 새로 공개하지 못한다
    scenarios = [await make_public(client, me) for _ in range(3)]
    for scenario in scenarios:
        await sanction(client, operator, scenario)
    notices = await outgoing(session)

    # 둘째 제재로 저절로 금지되었다. 셋째는 이미 금지 중이라 금지의 알림이 다시 가지 않는다
    assert [(notice.kind, notice.payload.get('publishing_banned')) for notice in notices] == [
        ('scenario.sanctioned', False),
        ('scenario.sanctioned', True),
        ('publishing.banned', None),
        ('scenario.sanctioned', True),
    ]
    assert notices[2].payload == {'automatic': True}
    assert {notice.user_id for notice in notices} == {ME}
    # 저절로 오른 금지는 원인인 제재의 기록 번호를 쓴다. kind 가 달라 그 제재의 알림과 겹치지 않는다
    assert notices[2].source_key.split(':')[1] == notices[1].source_key.split(':')[1]


async def test_an_operator_ban_and_lift_are_told(client: AsyncClient, operator: dict, session: AsyncSession):
    await ban(client, operator, ME)
    await ban(client, operator, ME, lift=True)
    await ban(client, operator, ME)

    notices = await outgoing(session)

    assert [(notice.kind, notice.payload) for notice in notices] == [
        ('publishing.banned', {'automatic': False}),
        ('publishing.unbanned', {}),
        ('publishing.banned', {'automatic': False}),
    ]
    # 같은 사람을 다시 금지해도 감사 기록이 달라 알림 서버에서 다른 알림이다
    assert len({notice.source_key for notice in notices}) == 3


async def test_the_reason_and_the_operator_are_not_told(
    app: FastAPI, client: AsyncClient, me: dict, operator: dict, session: AsyncSession
):
    app.state.settings.publishing_ban_threshold = 1
    await sanction_many(client, me, operator, 1)
    await ban(client, operator, ME, lift=True)

    payloads = str([notice.payload for notice in await outgoing(session)])

    # 사유는 감사 기록의 글이다. 신고한 사람이 드러날 수 있다
    assert REASON['reason'] not in payloads
    assert str(OPERATOR) not in payloads


async def test_a_refused_sanction_tells_nothing(client: AsyncClient, me: dict, operator: dict, session: AsyncSession):
    not_public = await ready_to_publish(client, me)
    await sanction(client, operator, not_public)
    await ban(client, operator, ME, lift=True)
    await sanction(client, operator, {'id': str(uuid.uuid4())})

    # 공개 중이 아닌 시나리오(409), 금지 중이 아닌 사람을 풀기(409), 없는 시나리오(404)는 제재가 아니다
    assert await outgoing(session) == []


async def test_ending_a_table_tells_nobody(client: AsyncClient, me: dict, operator: dict, session: AsyncSession):
    scenario = await make_public(client, me)
    table = (await open_table(client, me, scenario)).json()

    await client.post(f'{ADMIN_URL}/tables/{table["id"]}/end', json=REASON, headers=operator)

    # 앉은 사람이 테이블의 이벤트로 본다
    assert await outgoing(session) == []


def test_the_key_needs_a_saved_action():
    with pytest.raises(ValueError, match='flush'):
        action_key('publishing.banned', OperatorAction())
