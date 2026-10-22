# chat-server/app/catalog/schemas.py

"""
모델 목록 API 가 내보내는 응답의 모양. 대화에 싣는 모델(app/conversations/schemas.py)도 이 모양을 쓴다.

판매가(말 한 번에 몇 크레딧)는 아직 없다. 결제 서버의 가격 목록을 붙이는 PR 이 더한다.
원가, 창구, API 모델 이름은 내보내지 않는다. 운영의 정보다.
"""

from datetime import date

from ai_core.catalog_contract import Grade
from pydantic import BaseModel


class ModelOut(BaseModel):
    """고를 수 있는 모델 하나."""

    slug: str
    display_name: str
    vendor: str
    grade: Grade
    # 성인 등급의 대화에 고를 수 있나. 화면이 성인 등급의 대화에서 이것이 거짓인 모델을 감춘다
    allows_adult: bool
    # 이 날부터 쓰지 않는다. 화면이 "12월 1일 종료"를 보여 준다. 정해지지 않았으면 None
    retires_on: date | None


class ModelList(BaseModel):
    """고를 수 있는 모델들. 회사, 이름표 순서다."""

    items: list[ModelOut]
