# story-server/tests/reporting.py

"""
신고의 테스트가 함께 쓰는 것(tests/test_message_reports_api.py, tests/test_report_operators_api.py).
말을 주고받은 세션을 만들고, 말을 읽고, 신고한다.
"""

import asyncio

from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from tests.assets import FakeAsset
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, start_with_luna, turn_on_luna

MESSAGES_URL = f'{API_PREFIX}/messages'
# 모델의 답. 서술 하나와 미나의 말 하나다
ANSWER = '@narration: 바람이 분다.\n@mina: 위험한 답.'


async def say(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, content: str) -> None:
    """말을 하나 보내고 답이 끝나기를 기다린다."""
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': content}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))


async def messages(client: AsyncClient, headers: dict, conversation: dict) -> list[dict]:
    """세션의 지금 가지의 말들."""
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()['messages']


async def report(client: AsyncClient, headers: dict, message: dict, reason: str = 'minor', description: str = ''):
    """말 하나를 신고한다."""
    body = {'reason': reason, 'description': description}
    return await client.post(f'{MESSAGES_URL}/{message["id"]}/reports', json=body, headers=headers)


async def talk(client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, headers: dict) -> dict:
    """말을 넷 주고받은 세션. 답은 늘 ANSWER 이고 마지막 말은 모델의 답이다."""
    app.state.model_router = FakeRouter(ScriptedProvider(pieces=[ANSWER]))
    await turn_on_luna(session)
    conversation = await start_with_luna(client, asset, headers)
    for number in range(4):
        await say(client, app, headers, conversation, f'말 {number}')
    return conversation
