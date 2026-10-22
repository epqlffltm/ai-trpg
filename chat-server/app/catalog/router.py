# chat-server/app/catalog/router.py

"""
모델 목록 API. 대화에 고를 수 있는 모델들을 내준다.

    GET /api/v1/chat/models    고를 수 있는 모델들(켜져 있고 은퇴하지 않았다)

로그인을 요구한다. 다른 주소와 같다. 성인 등급을 볼 수 없는 사람에게도 allows_adult 를 그대로 싣는다.
모델의 속성일 뿐이고, 성인 등급의 대화를 거르는 것은 대화를 만들고 읽는 곳이다.
"""

from fastapi import APIRouter, status
from server_core.auth.dependencies import CurrentUser

from app.catalog import service
from app.catalog.models import AiModel
from app.catalog.schemas import ModelList, ModelOut
from app.core.dependencies import Session, Today

router = APIRouter(prefix='/models', tags=['models'])


def to_model_out(model: AiModel) -> ModelOut:
    """모델을 응답의 모양으로."""
    return ModelOut.model_validate(model, from_attributes=True)


@router.get('', response_model=ModelList, status_code=status.HTTP_200_OK)
async def list_models(user: CurrentUser, session: Session, today: Today) -> ModelList:
    """대화에 고를 수 있는 모델들. 회사, 이름표 순서다."""
    return ModelList(items=[to_model_out(model) for model in await service.offered_models(session, today)])
