# story-server/tests/turns.py

"""
말 보내기의 테스트들이 함께 쓰는 도우미. 테스트 모델(luna)을 켜고, 그 모델로 세션을 시작한다.

세계관은 집에서 아침에 시작한다. 미나는 집에, 준은 해변에 산다. 그래서 처음 장면의 인물은 미나 하나다.
"""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from ai_core.catalog_contract import Grade, Provider, TokenLimitField
from ai_core.catalog_file import CostEntry, ModelEntry
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import service as catalog
from app.main import API_PREFIX
from tests.assets import FakeAsset, make_world
from tests.catalog_rows import add_cost, put_models
from tests.engine_worlds import member

CONVERSATIONS_URL = f'{API_PREFIX}/conversations'
ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
LUNA = ModelEntry(
    slug='luna',
    provider=Provider.OPENAI,
    api_model_id='luna-2026-09-22',
    display_name='LUNA',
    vendor='openai',
    grade=Grade.STANDARD,
    token_limit_field=TokenLimitField.MAX_COMPLETION_TOKENS,
)
# luna 의 가격표 이름
PRICE_CODE = 'story.luna.i0.o0'
# 미나는 집에, 준은 해변에 산다
WORLD_FIELDS = {
    'slots': [{'id': 'morning', 'name': '아침', 'start_hour': 7}, {'id': 'night', 'name': '밤', 'start_hour': 19}],
    'start_slot': 'morning',
    'places': [{'id': 'home', 'name': '집'}, {'id': 'beach', 'name': '해변'}],
    'start_place': 'home',
    'cast': [
        {**member('mina', home='home'), 'character': {'name': '미나'}},
        {**member('jun', home='beach'), 'character': {'name': '준'}},
    ],
    'events': [],
    'endings': [],
}


def bearer(signing_key: SigningKey, user_id: uuid.UUID = ME) -> dict[str, str]:
    """그 사람의 access 토큰을 실은 머리말."""
    return {'Authorization': f'Bearer {make_token(signing_key, make_access_claims(sub=str(user_id)))}'}


async def turn_on_luna(session: AsyncSession) -> None:
    """luna 를 들여오고 오늘의 원가를 적어 켠다."""
    await put_models(session, LUNA)
    today = datetime.now(UTC).date()
    cost = CostEntry(input_per_mtok=Decimal('1'), output_per_mtok=Decimal('5'), effective_from=today, checked_on=today)
    await add_cost(session, 'luna', cost)
    await catalog.enable_model(session, 'luna', today)


async def start_with_luna(client: AsyncClient, asset: FakeAsset, headers: dict, fields: dict | None = None) -> dict:
    """luna 로 세션을 시작한다. 말은 아직 없다. fields 로 판의 칸을 덮어쓴다."""
    world = asset.add_world(make_world(fields={**WORLD_FIELDS, **(fields or {})}))
    body = {'world_id': str(world.id), 'model': 'luna'}
    response = await client.post(CONVERSATIONS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def parse_sse(text: str) -> list[tuple[str, dict]]:
    """SSE 의 글을 (event, data) 들로. 주석은 뺀다."""
    events = []
    for block in text.strip().split('\n\n'):
        fields = dict(line.split(': ', 1) for line in block.split('\n') if not line.startswith(':'))
        if fields:
            events.append((fields['event'], json.loads(fields['data'])))
    return events
