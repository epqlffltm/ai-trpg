# game-server/tests/narration_model.py

"""
테스트가 함께 쓰는 서술 모델. 시나리오는 추천 서술 모델이 있어야 저장된다(app/assets/scenarios/recommended_model.py).

clean_tables 가 테이블을 비운 뒤 모델 목록에 이 모델 하나를 켜 둔다(conftest.py). 결제 서버 없이 도는 테스트에서는
켜진 모델이 모두 고를 수 있는 모델이고, 가짜 결제 서버(tests/billing.py)는 이 모델의 가격표를 판다.
회사는 테스트 전용(test)이라 다른 회사의 대체 모델을 고르는 테스트에 끼어들지 않는다.

시나리오를 만드는 본문에는 with_model 로 이 모델을 더한다.
"""

from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.catalog_contract import Provider
from app.billing.price_list import FreePriceList
from app.billing.prices import narration_code
from app.catalog.models import AiModel, Grade
from app.tables.model_picker import ModelPicker

TEST_MODEL = 'test-narrator'
TEST_VENDOR = 'test'
# 테스트의 테이블이 거는 서술 값의 가격표 이름
TEST_PRICE_CODE = narration_code(TEST_MODEL)


def with_model(body: dict, model: str = TEST_MODEL) -> dict:
    """시나리오를 만드는 본문에 추천 서술 모델을 더한다. 본문에 이미 있으면 그 값을 둔다."""
    return {'narration_model': model, **body}


# 켜 둔 테스트 모델의 칸들. 서버 곁의 창구라 키가 없어도 된다(가짜 서술자는 부르지도 않는다)
TEST_MODEL_ROW = {
    'slug': TEST_MODEL,
    'provider': Provider.LOCAL.value,
    'api_model_id': TEST_MODEL,
    'display_name': '테스트 서술자',
    'vendor': TEST_VENDOR,
    'grade': Grade.STANDARD.value,
    'supports_reasoning': False,
    'supports_temperature': True,
    'enabled': True,
}


async def add_test_model(engine: AsyncEngine) -> None:
    """모델 목록에 테스트 모델을 넣는다. 테이블을 비운 뒤에 부른다."""
    async with engine.begin() as connection:
        await connection.execute(AiModel.__table__.insert().values(**TEST_MODEL_ROW))


def today() -> date:
    """오늘(UTC). 서비스를 바로 부르는 테스트가 시나리오를 저장할 때 은퇴했는지 볼 날로 넘긴다."""
    return datetime.now(UTC).date()


def free_picker() -> ModelPicker:
    """결제 서버 없이 도는 서버의 모델 고르기. 서비스를 바로 부르는 테스트가 테이블을 만들 때 넘긴다."""
    return ModelPicker(prices=FreePriceList(), now=datetime.now(UTC))


def asset_body(url: str, body: dict) -> dict:
    """자산을 만드는 본문. 시나리오의 주소면 추천 서술 모델을 더한다. 주소로 종류를 고르는 도우미가 쓴다."""
    return with_model(body) if url.endswith('/scenarios') else body
