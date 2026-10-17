# game-server/app/catalog/schemas.py

"""
모델 목록이 받는 입력의 모양. 관리 명령(scripts/models.py)이 만들어 넘기고, 나중의 관리 API 는 요청의 본문으로 받는다.

모양만 본다. 이미 있는 이름표인지처럼 DB 를 봐야 아는 것은 서비스가 본다(app/catalog/service.py).
"""

from datetime import date
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.catalog.models import Grade, Provider, TokenLimitField
from app.catalog.rules import token_field_problem

# 이름표. 영어 소문자와 숫자를 붙임표로 잇는다. 점은 쓰지 않는다. 결제 서버의 가격 코드에서 점이 칸을 나눈다.
# narration.<이름표>.i0.o0 이 결제 서버의 가격 코드 길이(64자) 안에 들도록 48자까지다
SLUG_PATTERN = r'^[a-z0-9]+(-[a-z0-9]+)*$'
SLUG_MAX_LENGTH = 48
Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN, max_length=SLUG_MAX_LENGTH)]
# API 에 보내는 모델 이름. 공백이 없다
ApiModelId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r'^\S+$', max_length=200)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
# 회사. 목록을 묶어 보이는 이름이다(openai, anthropic, google, moonshot …)
Vendor = Annotated[str, StringConstraints(pattern=r'^[a-z][a-z0-9-]*$', max_length=30)]
# 단가. USD, 백만 토큰당
Price = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=6)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ModelCreate(BaseModel):
    """새 모델. 꺼진 채로 들어간다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    slug: Slug
    provider: Provider
    api_model_id: ApiModelId
    display_name: DisplayName
    vendor: Vendor
    grade: Grade
    supports_reasoning: bool = False
    supports_temperature: bool = True
    token_limit_field: TokenLimitField | None = None

    @model_validator(mode='after')
    def token_field_fits_provider(self) -> Self:
        """출력 상한의 칸이 창구에 맞아야 한다."""
        problem = token_field_problem(self.provider, self.token_limit_field)
        if problem:
            raise ValueError(problem)
        return self


class ModelUpdate(BaseModel):
    """
    모델에서 바꿀 것. 적은 것만 바꾼다. 하나는 적어야 한다.

    이름표와 창구는 없다. 바꾸지 않는다(app/catalog/models.py).
    API 모델 이름(날짜판)도 없다. 날짜판은 SnapshotSwitch 로만 바꾼다. 바꾸면 모델이 꺼진다.
    출력 상한의 칸을 비우는 일도 없다. 칸을 적는 창구의 모델은 늘 칸이 있어야 하고, 아닌 창구의 모델은 늘 없다.
    """

    model_config = ConfigDict(extra='forbid', frozen=True)

    display_name: DisplayName | None = None
    vendor: Vendor | None = None
    grade: Grade | None = None
    supports_reasoning: bool | None = None
    supports_temperature: bool | None = None
    token_limit_field: TokenLimitField | None = None

    @model_validator(mode='after')
    def something_changes(self) -> Self:
        """바꿀 것이 하나는 있어야 한다."""
        if not self.changes():
            raise ValueError('바꿀 것이 없다')
        return self

    def changes(self) -> dict[str, object]:
        """적은 것만 칸 이름과 값으로."""
        return self.model_dump(exclude_none=True)


class CostCreate(BaseModel):
    """새 원가 단가. effective_from 부터 쓴다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    input_per_mtok: Price
    output_per_mtok: Price
    cached_input_per_mtok: Price | None = None
    cache_write_per_mtok: Price | None = None
    effective_from: date
    checked_on: date
    note: Note | None = None

    @model_validator(mode='after')
    def cached_input_is_not_dearer(self) -> Self:
        """캐시 읽기가 그냥 입력보다 비쌀 수는 없다. 칸을 바꿔 적은 것이다."""
        if self.cached_input_per_mtok is not None and self.cached_input_per_mtok > self.input_per_mtok:
            raise ValueError('캐시 읽기 단가가 입력 단가보다 비싸다. 칸을 바꿔 적지 않았나 본다')
        return self


class SnapshotSwitch(BaseModel):
    """날짜판 바꾸기. 새 API 모델 이름과 덧붙일 말."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    api_model_id: ApiModelId
    note: Note | None = None
