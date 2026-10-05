# game-server/app/assets/rulebooks/router.py

"""
룰북 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

규칙은 여기 없다. 누가 보낸 요청인지(토큰)와 입력의 모양만 확인하고 서비스에 맡긴다.
모든 주소가 로그인을 요구한다. 자기 룰북만 다룰 수 있다.
"""

import uuid

from fastapi import APIRouter, status

from app.assets.models import Rulebook
from app.assets.routing import Paging, Session, to_page, to_summary
from app.assets.rulebooks import service
from app.assets.rulebooks.schemas import RulebookCreate, RulebookDetail, RulebookUpdate
from app.assets.schemas import AssetPage
from app.auth.dependencies import CurrentUser
from app.engine.ruleset import Ruleset

router = APIRouter(prefix='/rulebooks', tags=['rulebooks'])


def to_detail(rulebook: Rulebook) -> RulebookDetail:
    """
    룰북을 만든 사람에게 보여 주는 응답으로 바꾼다. 진행 지침과 규칙까지 싣는다.

    규칙은 DB 에서 문서로 나온다. Ruleset 으로 읽어서 모양을 확인한 뒤에 내보낸다.
    """
    return RulebookDetail(
        **to_summary(rulebook.asset).model_dump(),
        gm_guide=rulebook.gm_guide,
        rules=Ruleset.model_validate(rulebook.rules),
    )


@router.post('', response_model=RulebookDetail, status_code=status.HTTP_201_CREATED)
async def create_rulebook(data: RulebookCreate, user: CurrentUser, session: Session) -> RulebookDetail:
    """룰북을 만든다. 만든 사람은 요청의 본문이 아니라 토큰에서 정해진다."""
    rulebook = await service.create_rulebook(session, user.user_id, data)
    return to_detail(rulebook)


@router.get('', response_model=AssetPage, status_code=status.HTTP_200_OK)
async def list_rulebooks(user: CurrentUser, session: Session, paging: Paging) -> AssetPage:
    """자기 룰북의 목록을 최근에 만든 것부터 돌려준다."""
    rulebooks, total = await service.list_rulebooks(session, user.user_id, paging.limit, paging.offset)
    return to_page(rulebooks, total)


@router.get('/{rulebook_id}', response_model=RulebookDetail, status_code=status.HTTP_200_OK)
async def read_rulebook(rulebook_id: uuid.UUID, user: CurrentUser, session: Session) -> RulebookDetail:
    """자기 룰북 하나를 돌려준다."""
    rulebook = await service.get_rulebook(session, user.user_id, rulebook_id)
    return to_detail(rulebook)


@router.patch('/{rulebook_id}', response_model=RulebookDetail, status_code=status.HTTP_200_OK)
async def update_rulebook(
    rulebook_id: uuid.UUID, data: RulebookUpdate, user: CurrentUser, session: Session
) -> RulebookDetail:
    """자기 룰북을 고친다. 보낸 칸만 바뀐다."""
    rulebook = await service.update_rulebook(session, user.user_id, rulebook_id, data)
    return to_detail(rulebook)


@router.delete('/{rulebook_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_rulebook(rulebook_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """자기 룰북을 지운다."""
    await service.delete_rulebook(session, user.user_id, rulebook_id)
