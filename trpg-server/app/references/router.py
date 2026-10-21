# trpg-server/app/references/router.py

"""
참고 자료 API(#482 4단계). 찾기와, 고른 줄을 내 로어북과 도감으로 복사하기.

복사의 주소는 로어북과 도감의 주소 아래에 둔다(/lorebooks/{id}/entries/copies). 결과가 그 로어북의 항목이라서다.
라우터는 여기 둔다. 로어북과 도감(app/assets/)은 참고 자료를 모르게 한다.
모든 주소가 로그인을 요구한다. 참고 자료는 누구나 찾고 복사한다. 넣는 곳은 자기 로어북과 도감뿐이다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse

from app.assets.bestiaries.router import to_monster_detail
from app.assets.lorebooks.router import to_entry_detail
from app.assets.routing import Paging, Session
from app.auth.dependencies import CurrentUser
from app.references import service
from app.references.copying import NotAMonsterError
from app.references.records import ReferenceKind, StoredReference
from app.references.schemas import (
    SEARCH_TEXT_MAX_LENGTH,
    LoreCopyResult,
    MonsterCopyResult,
    ReferenceCopy,
    ReferenceItem,
    ReferencePage,
)
from app.references.service import ReferenceNotFoundError

router = APIRouter()


def to_item(reference: StoredReference) -> ReferenceItem:
    """줄 하나를 응답의 모양으로. 보이는 이름과 글(한국어, 없으면 원본)이다."""
    return ReferenceItem(
        id=reference.id,
        source=reference.source,
        key=reference.key,
        kind=ReferenceKind(reference.kind),
        name=reference.shown_name,
        original_name=reference.name,
        content=reference.shown_content,
    )


async def handle_reference_not_found(request: Request, error: ReferenceNotFoundError) -> JSONResponse:
    """보낸 id 중 없는 줄이 있으면 404 다. 어느 것인지 싣는다. 앱에 한 번 등록한다(app/main.py)."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            'detail': '참고 자료를 찾을 수 없습니다.',
            'code': 'reference_not_found',
            'reference_ids': [str(reference_id) for reference_id in error.ids],
        },
    )


async def handle_not_a_monster(request: Request, error: NotAMonsterError) -> JSONResponse:
    """몬스터가 아닌 줄을 도감에 넣으려 하면 422 다. 그 줄의 key 를 싣는다. 앱에 한 번 등록한다(app/main.py)."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': '도감에는 몬스터만 넣을 수 있습니다.', 'code': 'not_a_monster', 'keys': error.keys},
    )


@router.get('/references', response_model=ReferencePage, status_code=status.HTTP_200_OK, tags=['references'])
async def search_references(
    user: CurrentUser,
    session: Session,
    paging: Paging,
    q: Annotated[str, Query(max_length=SEARCH_TEXT_MAX_LENGTH)] = '',
    kind: ReferenceKind | None = None,
) -> ReferencePage:
    """
    참고 자료를 이름(한국어 이름, 원본의 이름, 다른 이름)으로 찾는다. q 가 비면 전부다. kind 로 종류를 거른다.

    보이는 이름의 차례다. 쪽마다 출처 표시(attributions)가 함께 온다.
    """
    references, total = await service.search_references(session, q, kind, paging.limit, paging.offset)
    return ReferencePage(
        items=[to_item(reference) for reference in references],
        total=total,
        attributions=service.attributions_of(references),
    )


@router.post(
    '/lorebooks/{lorebook_id}/entries/copies',
    response_model=LoreCopyResult,
    status_code=status.HTTP_201_CREATED,
    tags=['lorebooks'],
)
async def copy_to_lorebook(
    lorebook_id: uuid.UUID, data: ReferenceCopy, user: CurrentUser, session: Session
) -> LoreCopyResult:
    """
    고른 참고 자료를 자기 로어북의 항목으로 복사한다. 물건은 물건, 몬스터는 종족 항목이다.

    이미 복사해 둔 줄은 건너뛴다(skipped). 다 넣으면 상한을 넘으면 하나도 넣지 않고 409 다.
    없는 줄이 있으면 404(reference_not_found)다.
    """
    outcome = await service.copy_to_lorebook(session, user.user_id, lorebook_id, data.reference_ids)
    return LoreCopyResult(created=[to_entry_detail(entry) for entry in outcome.created], skipped=outcome.skipped)


@router.post(
    '/bestiaries/{bestiary_id}/monsters/copies',
    response_model=MonsterCopyResult,
    status_code=status.HTTP_201_CREATED,
    tags=['bestiaries'],
)
async def copy_to_bestiary(
    bestiary_id: uuid.UUID, data: ReferenceCopy, user: CurrentUser, session: Session
) -> MonsterCopyResult:
    """
    고른 참고 자료(몬스터)를 자기 도감의 몬스터로 복사한다. 원본의 생물 분류를 도감의 타입으로 바꾼다.

    몬스터가 아닌 줄이 있으면 422(not_a_monster)다. 건너뛰기와 상한은 로어북과 같다.
    """
    outcome = await service.copy_to_bestiary(session, user.user_id, bestiary_id, data.reference_ids)
    return MonsterCopyResult(
        created=[to_monster_detail(monster) for monster in outcome.created], skipped=outcome.skipped
    )
