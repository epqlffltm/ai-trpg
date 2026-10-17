# game-server/app/catalog/lookup.py

"""
서술할 때 모델 목록에서 모델 하나를 찾는 것. 이름표로 찾고, 찾은 것은 DB 와 떨어진 값으로 돌려준다.

찾는 쪽(app/ai/routing.py)은 ModelLookup 의 모양만 안다.
지금 꽂는 것은 부를 때마다 DB 에서 한 줄 읽는 DbModelLookup 이다.
  - 서술은 테이블마다 라운드에 한 번이라 드물다. 이름표로 한 줄 읽는 것은 싸다.
  - 관리 명령으로 끄거나 날짜판을 바꾸면 다음 서술부터 바로 맞는다. 늦게 맞는 때가 없다.
나중에 서술이 잦아지면 같은 모양의 캐시(몇 분마다 새로 읽기)를 만들어 바꿔 꽂는다. 부르는 쪽은 바뀌지 않는다.
그래서 돌려주는 것을 ORM 객체가 아니라 바꾸지 못하는 값(CatalogModel)으로 한다.
ORM 객체는 세션에 묶여 있어서, 세션이 닫힌 뒤나 다른 작업에서 읽으면 깨진다. 캐시에 담아 두고 여럿이 읽을 수 없다.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.catalog import repository
from app.catalog.models import AiModel, Provider, TokenLimitField


@dataclass(frozen=True)
class CatalogModel:
    """모델 목록의 모델 하나. 부를 때 필요한 것만 담은 값이다."""

    slug: str
    provider: Provider
    api_model_id: str
    supports_reasoning: bool
    supports_temperature: bool
    token_limit_field: TokenLimitField | None
    enabled: bool
    retires_on: date | None


class ModelLookup(Protocol):
    """이름표로 모델을 찾는 것의 모양."""

    async def find(self, slug: str) -> CatalogModel | None:
        """그 이름표의 모델. 목록에 없으면 None."""
        ...


def to_value(model: AiModel) -> CatalogModel:
    """ORM 객체를 세션과 떨어진 값으로 옮긴다."""
    return CatalogModel(
        slug=model.slug,
        provider=Provider(model.provider),
        api_model_id=model.api_model_id,
        supports_reasoning=model.supports_reasoning,
        supports_temperature=model.supports_temperature,
        token_limit_field=TokenLimitField(model.token_limit_field) if model.token_limit_field else None,
        enabled=model.enabled,
        retires_on=model.retires_on,
    )


@dataclass(frozen=True)
class DbModelLookup:
    """찾을 때마다 DB 에서 한 줄 읽는다. 세션은 찾을 때마다 새로 열고 닫는다."""

    session_factory: async_sessionmaker[AsyncSession]

    async def find(self, slug: str) -> CatalogModel | None:
        """그 이름표의 모델. 목록에 없으면 None."""
        async with self.session_factory() as session:
            model = await repository.get_model(session, slug)
            return to_value(model) if model else None
