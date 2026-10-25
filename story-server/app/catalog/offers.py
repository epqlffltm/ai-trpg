# story-server/app/catalog/offers.py

"""
세션에 고를 수 있는 모델들. 모델 목록(DB)에서 켜져 있고 은퇴하지 않은 것이다(ai_core/catalog_contract.py 의 is_offered).

말 한 번의 값은 아직 없다. 결제 서버의 가격 목록(story.<이름표>.i0.o0)을 붙이는 것은 결제를 붙이는 PR 이 한다
(chat 서버의 app/catalog/offers.py 처럼 팔고 있는 것만 내주게 바뀐다).
성인 등급의 세션에 쓸 수 있나(allows_adult)는 여기서 거르지 않는다. 모델의 속성으로 싣고 화면이 거른다.
"""

from datetime import datetime

from ai_core.catalog_contract import is_offered
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import repository
from app.catalog.models import AiModel


async def list_offered(session: AsyncSession, now: datetime) -> list[AiModel]:
    """고를 수 있는 모델들. 회사, 이름표 순서다."""
    return [model for model in await repository.list_models(session) if is_offered(model, now.date())]
