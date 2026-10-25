# story-server/app/catalog/choice.py

"""
세션에 어느 모델을 쓸 수 있는가(docs/architecture/chat-server.md 의 "모델", "성인 콘텐츠"). DB 도 시계도 모른다.

  - 고를 수 있는 모델: 켜져 있고 은퇴하지 않았다(ai_core/catalog_contract.py 의 is_offered).
  - 성인 등급의 세션에는 그중 allows_adult 가 참인 모델만 고른다.
  - 모델을 고르거나 바꿀 때 한 번만 본다. 말을 보낼 때는 켜짐과 은퇴만 다시 본다(그 길을 만드는 PR).
  - 약관이 성적인 콘텐츠를 막는다고 확인된 창구의 모델은 allows_adult 를 켜지 않는다.
    켜면 키나 계정이 제재될 수 있다. 전체 이용가의 세션에는 그대로 쓴다.
"""

from datetime import date
from typing import Protocol

from ai_core.catalog_contract import Provider, is_offered

from app.ratings import Rating

# 약관이 성적인 콘텐츠를 막는다고 확인된 창구(2026-10-21 의 조사). 창구의 약관을 따른다.
# DeepSeek 은 그 회사의 창구를 쓰지 않아(deepinfra) 여기 없다. 켜기 전에 운영자가 deepinfra 의 약관을 본다
ADULT_REFUSING_PROVIDERS = frozenset({Provider.ANTHROPIC, Provider.GEMINI})


class ChoosableModel(Protocol):
    """고를 수 있나를 볼 때 쓰는 칸들. 모델의 ORM 객체(app/catalog/models.py 의 AiModel)가 맞는다."""

    @property
    def provider(self) -> str: ...

    @property
    def enabled(self) -> bool: ...

    @property
    def retires_on(self) -> date | None: ...

    @property
    def allows_adult(self) -> bool: ...


def may_allow_adult(model: ChoosableModel) -> bool:
    """성인 등급의 세션에 쓰게 켤 수 있는 창구인가."""
    return model.provider not in ADULT_REFUSING_PROVIDERS


def suits_rating(model: ChoosableModel, rating: Rating) -> bool:
    """그 등급의 세션에 쓸 수 있나. 전체 이용가는 모든 모델, 성인은 allows_adult 가 참인 모델이다."""
    return rating != Rating.ADULT or model.allows_adult


def is_choosable(model: ChoosableModel, rating: Rating, today: date) -> bool:
    """그날 그 등급의 세션에 고를 수 있나."""
    return is_offered(model, today) and suits_rating(model, rating)
