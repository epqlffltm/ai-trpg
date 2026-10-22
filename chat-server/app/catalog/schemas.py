# chat-server/app/catalog/schemas.py

"""
모델 목록 API 가 내보내는 응답의 모양. 게임 서버의 서술 모델 목록(GET /tables/narration-models)과 값의 칸이 같다.

원가, 창구, API 모델 이름은 내보내지 않는다. 운영의 정보다.
"""

from datetime import date, datetime

from ai_core.catalog_contract import Grade
from pydantic import BaseModel

from app.billing.prices import Tier


class NextPriceOut(BaseModel):
    """예약된 값의 바뀜. credits 가 null 이면 effective_at 부터 팔지 않는다."""

    credits: str | None
    tier: Tier | None
    # 그때부터의 값도 행사가인가
    promo: bool
    effective_at: datetime


class ModelOut(BaseModel):
    """
    고를 수 있는 모델 하나와 말 한 번의 값.

    credits 는 결제 서버가 정한 값(글자, "30")이다. 결제 서버 없이 도는 서버면 credits 와 tier 가 null 이다.
    tier 가 premium 이면 골드(유료 크레딧)로만 낸다. grade 는 화면의 묶음(basic, standard, premium)이다.
    """

    slug: str
    display_name: str
    vendor: str
    grade: Grade
    # 성인 등급의 대화에 고를 수 있나. 화면이 성인 등급의 대화에서 이것이 거짓인 모델을 감춘다
    allows_adult: bool
    # 이 날부터 쓰지 않는다. 화면이 "12월 1일 종료"를 보여 준다. 정해지지 않았으면 None
    retires_on: date | None
    credits: str | None
    tier: Tier | None
    # 지금 값이 행사가인가. 행사가면 next 가 행사가 끝나는 때와 그 뒤의 값이다(화면이 "11월 21일까지, 그 뒤 40")
    promo: bool
    next: NextPriceOut | None


class ModelList(BaseModel):
    """고를 수 있는 모델들. 회사, 이름표 순서다. free 는 결제 서버 없이 도는 서버라 값이 없다는 뜻이다."""

    free: bool
    items: list[ModelOut]
