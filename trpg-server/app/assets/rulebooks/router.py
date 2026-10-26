# trpg-server/app/assets/rulebooks/router.py

"""
룰북 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

규칙은 여기 없다. 누가 보낸 요청인지(토큰)와 입력의 모양만 확인하고 서비스에 맡긴다.
모든 주소가 로그인을 요구한다. 자기 룰북만 다룰 수 있다.
"""

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from server_core.auth.dependencies import CurrentUser

from app.assets.models import Rulebook
from app.assets.routing import Paging, Session, to_page, to_summary
from app.assets.rulebooks import service
from app.assets.rulebooks.schemas import (
    RulebookCreate,
    RulebookDetail,
    RulebookUpdate,
    TemplateList,
    TemplateSummary,
)
from app.assets.schemas import AssetPage
from app.engine.ruleset import Ruleset
from app.engine.templates import DEFAULT_TEMPLATE, Template, TemplateFile

router = APIRouter(prefix='/rulebooks', tags=['rulebooks'])


async def handle_rules_invalid(request: Request, error: service.RulesInvalidError) -> JSONResponse:
    """
    고친 규칙이 규칙 한 벌로 맞지 않으면 422 로 답한다(#804). 앱에 한 번 등록한다(app/main.py).

    수치의 최대에 쓰는 능력치가 규칙에 없거나 같은 수치가 두 번 있다. field 는 resources 다.
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': error.message, 'field': 'resources'},
    )


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


def to_template_summary(template: TemplateFile) -> TemplateSummary:
    """템플릿 파일 하나를 목록의 한 줄로 바꾼다."""
    return TemplateSummary(
        key=Template(template.key),
        name=template.name,
        summary=template.summary,
        attribution=list(template.attribution),
        notes=list(template.notes),
        rules=template.rules,
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


@router.get('/templates', response_model=TemplateList, status_code=status.HTTP_200_OK)
async def list_templates(user: CurrentUser) -> TemplateList:
    """
    룰북을 만들 때 고를 수 있는 템플릿들과 그 규칙(#615). 다른 주소처럼 로그인을 요구한다(user 는 쓰지 않는다).

    룰북의 길(/{rulebook_id})보다 먼저 등록한다. templates 를 룰북의 id 로 읽지 않게 한다.
    """
    items = [to_template_summary(template) for template in service.list_templates()]
    return TemplateList(default=DEFAULT_TEMPLATE, items=items)


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
