# trpg-server/app/catalog/lookup.py

"""
서술할 때 모델 목록에서 모델 하나를 찾는 것. 이름표로 찾고, 찾은 것은 DB 와 떨어진 값으로 돌려준다.

찾는 쪽(app/ai/routing.py)은 ModelLookup 의 모양만 안다. 그 모양과 돌려주는 값(CatalogModel, UnitCost)은
모델 목록의 계약(app/ai/catalog_contract.py)에 있다. 여기는 그것을 DB 로 채우는 구현이다.
지금 꽂는 것은 부를 때마다 DB 에서 한 줄 읽는 DbModelLookup 이다.
  - 서술은 테이블마다 라운드에 한 번이라 드물다. 이름표로 한 줄 읽는 것은 싸다.
  - 관리 명령으로 끄거나 날짜판을 바꾸면 다음 서술부터 바로 맞는다. 늦게 맞는 때가 없다.
나중에 서술이 잦아지면 같은 모양의 캐시(몇 분마다 새로 읽기)를 만들어 바꿔 꽂는다. 부르는 쪽은 바뀌지 않는다.
그래서 돌려주는 것을 ORM 객체가 아니라 바꾸지 못하는 값(CatalogModel)으로 한다.
ORM 객체는 세션에 묶여 있어서, 세션이 닫힌 뒤나 다른 작업에서 읽으면 깨진다. 캐시에 담아 두고 여럿이 읽을 수 없다.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.catalog_contract import CatalogModel, Provider, ReasoningStyle, TokenLimitField, UnitCost
from app.catalog import repository
from app.catalog.models import AiModel, AiModelCost


def cost_value(cost: AiModelCost) -> UnitCost:
    """단가의 ORM 객체를 세션과 떨어진 값으로 옮긴다."""
    return UnitCost(
        cost_id=cost.id,
        input_per_mtok=cost.input_per_mtok,
        output_per_mtok=cost.output_per_mtok,
        cached_input_per_mtok=cost.cached_input_per_mtok,
        cache_write_per_mtok=cost.cache_write_per_mtok,
    )


def to_value(model: AiModel, cost: AiModelCost | None = None) -> CatalogModel:
    """ORM 객체(모델과 그날의 단가)를 세션과 떨어진 값으로 옮긴다."""
    return CatalogModel(
        slug=model.slug,
        provider=Provider(model.provider),
        api_model_id=model.api_model_id,
        supports_reasoning=model.supports_reasoning,
        supports_temperature=model.supports_temperature,
        token_limit_field=TokenLimitField(model.token_limit_field) if model.token_limit_field else None,
        enabled=model.enabled,
        retires_on=model.retires_on,
        cost=cost_value(cost) if cost else None,
        reasoning_style=ReasoningStyle(model.reasoning_style) if model.reasoning_style else None,
    )


@dataclass(frozen=True)
class DbModelLookup:
    """찾을 때마다 DB 에서 읽는다(모델 한 줄, 그날의 단가 한 줄). 세션은 찾을 때마다 새로 열고 닫는다."""

    session_factory: async_sessionmaker[AsyncSession]

    async def find(self, slug: str, day: date) -> CatalogModel | None:
        """그 이름표의 모델과 그날의 단가. 목록에 없으면 None."""
        async with self.session_factory() as session:
            model = await repository.get_model(session, slug)
            if model is None:
                return None
            return to_value(model, await repository.cost_on(session, slug, day))
