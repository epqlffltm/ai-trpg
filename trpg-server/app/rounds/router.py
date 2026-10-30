# trpg-server/app/rounds/router.py

"""
라운드 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

주소는 테이블 아래에 둔다(/tables/{table_id}/rounds). 라운드는 테이블에 딸린 것이다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status
from fastapi.responses import JSONResponse
from server_core.auth.dependencies import CurrentUser

from app.assets.routing import Paging, Session
from app.billing.models import NarrationCharge
from app.core.dice import Rolling
from app.engine.resources import is_open
from app.engine.ruleset import ResourceHolder, Ruleset
from app.rounds import service, state, trades
from app.rounds.cast import Scene, is_named
from app.rounds.closing import RoundCloser, closer_of
from app.rounds.errors import ActionNotInRulesError, ActionTargetError, RoundConflictError, RoundNotFoundError
from app.rounds.models import Declaration, Round, RoundStatus
from app.rounds.monster_scene import condition as monster_condition
from app.rounds.schemas import (
    CarriedOut,
    ChargeOut,
    DeclarationOut,
    DeclarationUpdate,
    PersonOut,
    RoundOut,
    RoundPage,
    RoundPriceOut,
    SceneCastOut,
    SceneMonsterOut,
)
from app.tables import injuries, monster_items, npc_items, resources
from app.tables.carried import Carried
from app.tables.items import CatalogItem
from app.tables.models import GameTable, TableStatus
from app.tables.resources import Bearer
from app.tables.schemas import ResourceOut

router = APIRouter(prefix='/tables/{table_id}/rounds', tags=['rounds'])


def get_closer(request: Request) -> RoundCloser:
    """
    서술을 뒤에서 돌게 맡기는 것을 만든다. 앱에 꽂아 둔 서술자와 작업 관리자를 쓴다(app/main.py).

    요청마다 새로 만든다. 테스트가 서술자를 바꿔 꽂으면 그 뒤의 요청부터 바뀐 것을 쓴다.
    """
    return closer_of(request.app.state)


# 라운드를 닫을 수 있는 API 가 인자의 형식으로 쓴다
Closing = Annotated[RoundCloser, Depends(get_closer)]

# 라운드의 번호. 1 부터다
RoundNumber = Annotated[int, Path(ge=1)]


def to_price(round_: Round) -> RoundPriceOut | None:
    """라운드에 알린 1인 1라운드의 값. 알리지 못했으면 None."""
    if round_.announced_credits is None:
        return None
    return RoundPriceOut(credits=round_.announced_credits, tier=round_.announced_tier)


def to_charge(charge: NarrationCharge) -> ChargeOut:
    """청구 하나를 앉은 사람에게 보여 주는 응답으로. 이름표와 가격표 이름, 실패의 까닭은 싣지 않는다."""
    return ChargeOut(user_id=charge.payer_id, status=charge.status, credits=charge.held_credits)


# 결과 중 바뀐 수치를 싣는 것들(#804). 쉬기, 물건을 쓰기, 던지기, 기술을 쓰기(#805)다
SHIFTING_OUTCOMES = ('rest', 'item_use', 'item_throw', 'skill_use')
# 그 안에서 바뀐 수치의 목록인 칸들. 맞춘 수치(resources)와 기술의 비용(cost, #805)이다
SHIFT_LISTS = ('resources', 'cost')


def visible_part(part: dict, viewer_id: uuid.UUID) -> dict:
    """결과 하나(쉬기, 물건, 기술)에서 그 사람이 숫자로 보지 못하는 수치의 바뀐 것을 뺀다."""
    lists = {key: resources.visible_shifts(part[key], viewer_id) for key in SHIFT_LISTS if part.get(key)}
    return {**part, **lists}


def visible_outcome(outcome: dict | None, viewer_id: uuid.UUID) -> dict | None:
    """
    선언의 결과에서 그 사람이 숫자로 보지 못하는 수치의 바뀐 것을 뺀다(#804). 저장된 결과는 고치지 않는다.
    가기에서 터진 덫(#806)이 맞춘 수치도 같다.
    """
    if outcome is None:
        return None
    changed = {
        key: visible_part(outcome[key], viewer_id)
        for key in SHIFTING_OUTCOMES
        if isinstance(outcome.get(key), dict) and any(outcome[key].get(one) for one in SHIFT_LISTS)
    }
    move = outcome.get('move')
    if isinstance(move, dict) and move.get('traps'):
        changed['move'] = {**move, 'traps': [visible_part(trap, viewer_id) for trap in move['traps']]}
    return {**outcome, **changed} if changed else outcome


def to_round(table: GameTable, round_: Round, viewer_id: uuid.UUID) -> RoundOut:
    """
    라운드를 앉은 사람에게 보여 주는 응답으로 바꾼다.

    선언을 받는 동안에는 남의 선언의 글과 행동을 가린다. 누가 냈는지만 보인다.
    선언을 마감하면(닫는 중부터) 모두의 것이 보인다. 그때는 이벤트 기록에도 적혀 있다.
    """
    is_open = round_.status == RoundStatus.OPEN

    def can_see(declaration: Declaration) -> bool:
        """보는 사람이 이 선언의 글과 행동을 볼 수 있는가."""
        return not is_open or declaration.user_id == viewer_id

    declarations = [
        DeclarationOut(
            user_id=declaration.user_id,
            character_name=declaration.character_name,
            content=declaration.content if can_see(declaration) else None,
            action=declaration.action if can_see(declaration) else None,
            # 결과는 가리지 않는다. 열려 있는 동안에는 어차피 없고, 마감한 뒤에는 모두에게 보인다.
            # 숨긴 수치(#804)의 바뀐 것만 보는 사람에 따라 뺀다
            outcome=visible_outcome(declaration.outcome, viewer_id),
        )
        for declaration in round_.declarations
    ]
    # 진행 중인 테이블에서 선언을 받는 중일 때만 기다리는 사람이 있다
    is_waiting = is_open and table.status == TableStatus.PLAYING
    return RoundOut(
        number=round_.number,
        scene=round_.scene,
        status=round_.status,
        declarations=declarations,
        # 죽음의 굴림은 가리지 않는다. 열려 있는 동안에는 어차피 없고, 마감한 뒤에는 모두에게 보인다
        death_saves=round_.death_saves,
        arrivals=round_.arrivals,
        waiting_for=state.waiting_for(table, round_) if is_waiting else [],
        created_at=round_.created_at,
        deadline_at=round_.deadline_at,
        narration_model=round_.narration_model,
        input_step=round_.input_step,
        output_step=round_.output_step,
        price=to_price(round_),
        closing_at=round_.closing_at,
        closed_at=round_.closed_at,
        narration_failed_at=round_.narration_failed_at,
        narration_failures=round_.narration_failures,
    )


def to_carried(held: list[Carried], things: dict[uuid.UUID, CatalogItem]) -> list[CarriedOut]:
    """몬스터나 NPC 가 지금 지닌 것을 응답으로 바꾼다. 장비 다음 소지품의 차례다."""
    return [
        CarriedOut(
            entry_id=one.entry_id,
            name=things[one.entry_id].name,
            rarity=things[one.entry_id].rarity,
            count=one.count,
            equipped=one.equipped,
            price=things[one.entry_id].price,
        )
        for one in held
    ]


def open_resources(ruleset: Ruleset | None, bearer: Bearer, holder: ResourceHolder) -> list[ResourceOut]:
    """
    인물이나 몬스터의 수치 중 모두가 보는 것(#804). 규칙이 없으면(수치가 없는 판) 빈 목록이다.

    인물과 몬스터에는 주인이 없어, 가진 사람만 보는 수치도 아무도 숫자로 보지 않는다.
    """
    if ruleset is None:
        return []
    return [
        ResourceOut(
            key=level.resource.key,
            name=level.resource.name,
            value=level.value,
            min=level.resource.min,
            max=level.maximum,
        )
        for level in resources.levels_of(ruleset, bearer, holder)
        if is_open(level.resource)
    ]


def to_cast(
    round_: Round, scene: Scene, things: dict[uuid.UUID, CatalogItem], ruleset: Ruleset | None = None
) -> SceneCastOut:
    """
    이번 장면의 인물과 몬스터들을 앉은 사람에게 보여 주는 응답으로 바꾼다. 이름과 생사(와 몸 상태)를 싣는다.

    인물과 몬스터 모두 지닌 물건도 싣는다. things 는 판의 물건들이다(이름).
    판의 규칙(ruleset)이 있으면 모두가 보는 수치(#804)도 싣는다.
    """
    people = [
        PersonOut(
            id=member.entry_id,
            name=member.name,
            status=member.npc.status,
            injuries=injuries.active_keys(member.npc.injuries),
            named=is_named(member.npc),
            attitude=member.npc.attitude,
            items=to_carried(npc_items.carried(member.npc, member.definition), things),
            merchant=trades.is_merchant(member),
            place_id=member.npc.place_id,
            resources=open_resources(ruleset, member.npc, ResourceHolder.NPCS),
        )
        for member in scene.cast
    ]
    monsters = [
        SceneMonsterOut(
            id=monster.state.id,
            name=monster.name,
            place_id=monster.state.place_id,
            status=monster.state.status,
            condition=monster_condition(monster),
            injuries=injuries.active_keys(monster.state.injuries),
            items=to_carried(monster_items.carried(monster.state, monster.definition), things),
            resources=open_resources(ruleset, monster.state, ResourceHolder.MONSTERS),
        )
        for monster in scene.monsters
    ]
    return SceneCastOut(round=round_.number, people=people, monsters=monsters)


# --- 서비스의 예외를 응답으로 바꾼다. 앱에 한 번 등록한다(app/main.py) ---


async def handle_round_not_found(request: Request, error: RoundNotFoundError) -> JSONResponse:
    """ "그런 번호의 라운드가 없다"는 404 다."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '라운드를 찾을 수 없습니다.'})


async def handle_round_conflict(request: Request, error: RoundConflictError) -> JSONResponse:
    """ "테이블의 지금 상태와 부딪힌다"는 409 다. 이유를 reason 에 싣는다."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '테이블의 지금 상태에서는 할 수 없습니다.', 'reason': error.reason},
    )


async def handle_action_not_in_rules(request: Request, error: ActionNotInRulesError) -> JSONResponse:
    """ "행동이 이 테이블의 규칙에 없는 것을 가리킨다"는 422 다. 모양은 맞고, 적은 값이 틀렸다."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': f'action.{error.field} 가 이 테이블의 규칙에 없습니다.'},
    )


# 겨눌 수 없는 대상의 칸마다 알리는 말
TARGET_ERRORS = {
    'target': 'action.target 이 이 테이블에 앉은 사람이 아닙니다.',
    'npc': 'action.npc 가 이번 장면의 인물이 아니거나 다른 장소에 있습니다.',
    'place': 'action.place 가 지금 장소에서 아는 길로 이어진 장소가 아닙니다.',
    'monster': 'action.monster 가 지금 장소의 몬스터가 아닙니다.',
    'item': 'action.item 이 지금 장소에 보이게 놓인 물건이 아닙니다.',
    'carried': 'action.item 이 그 몬스터나 인물이 지금 지닌 물건이 아닙니다.',
    'carry': 'action.carry 가 같은 장소에 쓰러져 있는(죽지 않은) 다른 사람이 아닙니다.',
    'device': 'action.device 가 그 길의 문에 있는 장치(lock, bar)가 아니거나, 둘 다 있는 문인데 적지 않았습니다.',
}


async def handle_action_target(request: Request, error: ActionTargetError) -> JSONResponse:
    """ "행동의 대상을 겨눌 수 없다"는 422 다. 앉은 사람이 아니거나, 이번 장면의 인물이 아니다."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={'detail': TARGET_ERRORS[error.field]}
    )


# --- 읽기 ---


@router.get('', response_model=RoundPage, status_code=status.HTTP_200_OK)
async def list_rounds(table_id: uuid.UUID, user: CurrentUser, session: Session, paging: Paging) -> RoundPage:
    """테이블의 라운드를 처음 것부터 돌려준다. 지나간 이야기를 순서대로 읽는다."""
    table, rounds, total = await service.list_rounds(session, user.user_id, table_id, paging.limit, paging.offset)
    return RoundPage(items=[to_round(table, round_, user.user_id) for round_ in rounds], total=total)


# /current 를 /{number} 보다 먼저 적는다. 먼저 적은 주소가 먼저 맞춰진다
@router.get('/current', response_model=RoundOut, status_code=status.HTTP_200_OK)
async def read_current_round(table_id: uuid.UUID, user: CurrentUser, session: Session) -> RoundOut:
    """가장 최근 라운드를 돌려준다. 진행 중인 테이블에서는 지금 선언을 받고 있는 라운드다."""
    table, round_ = await service.get_current_round(session, user.user_id, table_id)
    return to_round(table, round_, user.user_id)


@router.get('/current/people', response_model=SceneCastOut, status_code=status.HTTP_200_OK)
async def read_scene_cast(table_id: uuid.UUID, user: CurrentUser, session: Session) -> SceneCastOut:
    """
    가장 최근 라운드의 장면에 나온 인물들을 돌려준다. 행동의 npc 칸에 이 목록의 id 를 적는다.

    자리가 있는 인물은 살아 있는 캐릭터가 서 있는 장소들의 인물, 없는 인물은 장면에 이름이나 호칭이 나온 인물만
    들어간다(#282). 테이블의 인물 전부가 아니다.
    """
    round_, scene, things, ruleset = await service.get_scene_cast(session, user.user_id, table_id)
    return to_cast(round_, scene, things, ruleset)


@router.get('/{number}/charges', response_model=list[ChargeOut], status_code=status.HTTP_200_OK)
async def read_round_charges(
    table_id: uuid.UUID, number: RoundNumber, user: CurrentUser, session: Session
) -> list[ChargeOut]:
    """
    라운드의 서술 값을 내는 사람마다의 청구. 앉은 사람만 본다. 라운드를 열 때 앉아 있던 사람 모두다.

    값(credits)은 결제 서버가 실제로 홀드한 값이다. 라운드를 연 뒤 몇 초 안에 걸린다. 그 전에는 null 이다.
    이 기록이 생기기 전에 연 라운드나 결제 서버 없이 도는 서버면 빈 목록이다.
    """
    charges = await service.get_round_charges(session, user.user_id, table_id, number)
    return [to_charge(charge) for charge in charges]


@router.get('/{number}', response_model=RoundOut, status_code=status.HTTP_200_OK)
async def read_round(table_id: uuid.UUID, number: RoundNumber, user: CurrentUser, session: Session) -> RoundOut:
    """라운드 하나를 번호로 돌려준다."""
    table, round_ = await service.get_round(session, user.user_id, table_id, number)
    return to_round(table, round_, user.user_id)


# --- 바꾸기 ---


@router.put('/current/declaration', response_model=RoundOut, status_code=status.HTTP_200_OK)
async def declare(
    table_id: uuid.UUID, data: DeclarationUpdate, user: CurrentUser, session: Session, closer: Closing, dice: Rolling
) -> RoundOut:
    """
    열려 있는 라운드에 선언을 낸다. 다시 내면 바뀐다.

    모두가 내면 라운드가 닫기 시작한다. 그때는 status 가 closing 인 라운드가 돌아온다.
    행동을 붙인 선언은 그때 판정된다. 결과가 선언의 outcome 에 실려 돌아온다.
    GM 의 서술은 뒤에서 돈다. 끝나서 다음 라운드가 열린 것은 스트림으로 온다.
    """
    table, round_ = await service.declare(session, user.user_id, table_id, data, closer, dice)
    return to_round(table, round_, user.user_id)


# 202: 접수했다는 뜻이다. 일은 아직 끝나지 않았다. 서술이 뒤에서 돈다
@router.post('/current/close', response_model=RoundOut, status_code=status.HTTP_202_ACCEPTED)
async def close_round(
    table_id: uuid.UUID, user: CurrentUser, session: Session, closer: Closing, dice: Rolling
) -> RoundOut:
    """
    방장이 라운드를 닫는다. 선언을 기다리지 않고 넘어간다. status 가 closing 인 라운드가 돌아온다.

    닫는 중인 채로 오래 멈춰 있는 라운드에 다시 부르면 서술을 다시 맡긴다. 판정은 다시 하지 않는다.
    """
    table, round_ = await service.force_close(session, user.user_id, table_id, closer, dice)
    return to_round(table, round_, user.user_id)
