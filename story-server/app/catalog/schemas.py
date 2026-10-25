# story-server/app/catalog/schemas.py

"""
모델 목록 API 가 내보내는 응답의 모양. chat 서버의 것과 같은 칸에서 값의 칸(credits, tier, promo, next)이 빠졌다.
값은 결제를 붙이는 PR 이 더한다. 원가, 창구, API 모델 이름은 내보내지 않는다. 운영의 정보다.
"""

from datetime import date

from ai_core.catalog_contract import Grade
from pydantic import BaseModel


class ModelOut(BaseModel):
    """고를 수 있는 모델 하나. grade 는 화면의 묶음(basic, standard, premium)이다."""

    slug: str
    display_name: str
    vendor: str
    grade: Grade
    # 성인 등급의 세션에 고를 수 있나. 화면이 성인 등급의 세션에서 이것이 거짓인 모델을 감춘다
    allows_adult: bool
    # 이 날부터 쓰지 않는다. 화면이 "12월 1일 종료"를 보여 준다. 정해지지 않았으면 None
    retires_on: date | None


class ModelList(BaseModel):
    """고를 수 있는 모델들. 회사, 이름표 순서다."""

    items: list[ModelOut]
