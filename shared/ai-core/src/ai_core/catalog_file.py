# shared/ai-core/src/ai_core/catalog_file.py

"""
모델 목록의 원본 파일(ai_core/model_catalog.toml)을 읽고 모양을 본다(#499).

모델 목록은 이 파일 하나가 원본이다. 서비스마다 관리 명령으로 자기 표에 들여온다(게임 서버는 scripts.models sync).
켜고 끄기, 회사의 대체 모델은 서비스의 표에서 한다. 파일에는 공급자가 정하는 것과 모두가 같이 보는 것만 둔다.
  - 이름표, 창구, API 모델 이름(날짜판), 보이는 이름, 회사, 분류
  - 모델이 받는 것(생각의 깊이, 온도, 출력 상한의 칸, 생각을 켜고 끄는 방식)
  - 은퇴일(공급자가 모델을 내리는 날)
  - 원가 단가들(USD, 백만 토큰당). 값이 바뀌면 줄을 지우지 않고 새 줄을 더한다

한 서비스에만 뜻이 있는 것(chat 의 성인 등급 허용 같은)은 여기 두지 않고 그 서비스의 표에 둔다.

파일의 format 이 이 코드가 아는 판(FORMAT)과 다르면 읽지 않는다. 칸의 뜻이 바뀌면 판을 올린다.
값은 Decimal 로 읽는다(TOML 의 실수를 float 로 읽으면 0.1 같은 값이 틀어진다).
틀린 곳이 있으면 CatalogFileError 하나로 모두 알린다. 하나라도 틀리면 아무것도 들여오지 않는다.
"""

import tomllib
from collections import Counter
from datetime import date
from decimal import Decimal
from importlib import resources
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

from ai_core.catalog_contract import (
    Grade,
    Provider,
    ReasoningStyle,
    TokenLimitField,
    reasoning_style_problem,
    token_field_problem,
)

# 이 코드가 읽는 파일의 판
FORMAT = 1
# 패키지에 든 원본 파일의 이름
CATALOG_FILE = 'model_catalog.toml'

# 이름표. 영어 소문자와 숫자를 붙임표로 잇는다. 점은 쓰지 않는다. 결제 서버의 가격 코드에서 점이 칸을 나눈다.
# narration.<이름표>.i0.o0 이 결제 서버의 가격 코드 길이(64자) 안에 들도록 48자까지다
SLUG_PATTERN = r'^[a-z0-9]+(-[a-z0-9]+)*$'
SLUG_MAX_LENGTH = 48
Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN, max_length=SLUG_MAX_LENGTH)]
# API 에 보내는 모델 이름. 공백이 없다
ApiModelId = Annotated[str, StringConstraints(pattern=r'^\S+$', max_length=200)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
# 회사. 목록을 묶어 보이는 이름이다(openai, anthropic, google, moonshot …)
Vendor = Annotated[str, StringConstraints(pattern=r'^[a-z][a-z0-9-]*$', max_length=30)]
# 단가. USD, 백만 토큰당. 소수 여섯째 자리까지(표의 칸과 같다)
Price = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=6)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class CatalogFileError(ValueError):
    """모델 목록의 파일을 읽을 수 없다. problems 는 틀린 곳마다 한 줄이다."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__('\n'.join(problems))
        self.problems = problems


class CostEntry(BaseModel):
    """원가 단가 하나. effective_from 부터 쓴다. checked_on 은 공식 가격표에서 확인한 날이다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    effective_from: date
    checked_on: date
    input_per_mtok: Price
    output_per_mtok: Price
    cached_input_per_mtok: Price | None = None
    cache_write_per_mtok: Price | None = None
    note: Note | None = None

    @model_validator(mode='after')
    def cached_input_is_not_dearer(self) -> Self:
        """캐시 읽기가 그냥 입력보다 비쌀 수는 없다. 칸을 바꿔 적은 것이다."""
        if self.cached_input_per_mtok is not None and self.cached_input_per_mtok > self.input_per_mtok:
            raise ValueError('캐시 읽기 단가가 입력 단가보다 비싸다. 칸을 바꿔 적지 않았나 본다')
        return self


class ModelEntry(BaseModel):
    """파일의 모델 하나."""

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
    reasoning_style: ReasoningStyle | None = None
    retires_on: date | None = None
    costs: tuple[CostEntry, ...] = ()

    @model_validator(mode='after')
    def fields_fit_provider(self) -> Self:
        """출력 상한의 칸과 생각을 켜고 끄는 방식이 창구에 맞아야 한다."""
        problem = token_field_problem(self.provider, self.token_limit_field) or reasoning_style_problem(
            self.provider, self.reasoning_style
        )
        if problem:
            raise ValueError(problem)
        return self

    @model_validator(mode='after')
    def one_cost_a_day(self) -> Self:
        """한 모델에 같은 날부터의 단가가 둘이면 어느 것이 맞는지 모른다."""
        days = [cost.effective_from for cost in self.costs]
        if len(days) != len(set(days)):
            raise ValueError('같은 날부터의 단가가 둘이다. 하나를 고친다')
        return self


def repeated(values: list[object]) -> list[object]:
    """두 번 넘게 나온 값들. 처음 나온 순서다."""
    return [value for value, count in Counter(values).items() if count > 1]


class ModelCatalog(BaseModel):
    """파일 전체. 판과 모델들."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    format: Literal[1]
    models: tuple[ModelEntry, ...] = ()

    @model_validator(mode='after')
    def slugs_are_unique(self) -> Self:
        """이름표는 하나씩이다."""
        twice = repeated([model.slug for model in self.models])
        if twice:
            raise ValueError(f'이름표가 두 번 나온다: {", ".join(map(str, twice))}')
        return self

    @model_validator(mode='after')
    def api_models_are_unique(self) -> Self:
        """같은 창구의 같은 API 모델을 두 이름표로 두지 않는다. 목록에 같은 모델이 둘 보인다."""
        twice = repeated([(model.provider, model.api_model_id) for model in self.models])
        if twice:
            names = ', '.join(f'{provider}:{api_model_id}' for provider, api_model_id in twice)
            raise ValueError(f'같은 창구의 같은 API 모델이 두 번 나온다: {names}')
        return self


def problem_lines(error: ValidationError) -> list[str]:
    """모양이 틀린 곳마다 한 줄. 몇째 모델의 어느 칸인지를 앞에 쓴다."""
    return [f'{".".join(str(part) for part in item["loc"]) or "파일"}: {item["msg"]}' for item in error.errors()]


def parse_catalog(text: str) -> ModelCatalog:
    """TOML 글을 모델 목록으로. 판이 다르거나 모양이 틀리면 CatalogFileError."""
    try:
        raw = tomllib.loads(text, parse_float=Decimal)
    except tomllib.TOMLDecodeError as error:
        raise CatalogFileError([f'TOML 이 아니다: {error}']) from error
    if raw.get('format') != FORMAT:
        raise CatalogFileError([f'이 코드가 읽는 판은 format = {FORMAT} 이다(파일은 {raw.get("format")!r})'])
    try:
        return ModelCatalog.model_validate(raw)
    except ValidationError as error:
        raise CatalogFileError(problem_lines(error)) from error


def bundled_text() -> str:
    """패키지에 든 원본 파일의 글."""
    return resources.files('ai_core').joinpath(CATALOG_FILE).read_text(encoding='utf-8')


def load_catalog(path: Path | None = None) -> ModelCatalog:
    """
    모델 목록을 읽는다. path 가 없으면 패키지에 든 원본 파일이다. 고친 파일을 들여오기 전에 볼 때 path 를 준다.

    읽을 수 없거나 틀렸으면 CatalogFileError.
    """
    try:
        text = bundled_text() if path is None else path.read_text(encoding='utf-8')
    except OSError as error:
        raise CatalogFileError([f'파일을 읽을 수 없다: {error}']) from error
    return parse_catalog(text)
