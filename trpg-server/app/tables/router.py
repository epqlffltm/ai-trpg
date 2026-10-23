# trpg-server/app/tables/router.py

"""
테이블 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

응답을 만들 때 테이블의 복사본에서 참가자에게 보여도 되는 것만 꺼낸다(to_detail).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from server_core.auth.dependencies import CurrentUser

from app.assets.models import PLAYER_MADE_MODES, CharacterMode
from app.assets.routing import Paging, Session
from app.assets.scenarios.schemas import PlayerMadeHp, RecommendedPlayers
from app.assets.scenarios.snapshot import (
    CrossSnapshot,
    CurrencySnapshot,
    ForceSnapshot,
    PickSnapshot,
    RouteSnapshot,
    Snapshot,
    cover_at,
    read_snapshot,
)
from app.billing.price_list import PriceListUnavailable
from app.billing.prices import Change
from app.billing.routing import Now, Prices
from app.calendar import clock
from app.calendar.responses import to_clock
from app.catalog import offers
from app.catalog.offers import OfferedModel, StepPrice
from app.catalog.steps import input_tokens, output_tokens
from app.core.dice import Rolling
from app.engine.check import find_difficulty
from app.engine.ruleset import Ruleset
from app.limits.routing import Limited
from app.personas import saving
from app.personas.router import to_persona
from app.personas.schemas import PersonaOut
from app.rounds import service as round_service
from app.rounds.router import Closing
from app.tables import (
    credit_waits,
    deaths,
    equipment,
    injuries,
    items,
    narration_models,
    place_items,
    places,
    quests,
    references,
    replacements,
    repository,
    rolls,
    route_locks,
    service,
    sheets,
    styles,
    time_limits,
    wearing,
    whisper_notices,
)
from app.tables.errors import (
    MemberNotFoundError,
    NotHostError,
    TableConflictError,
    TableNotFoundError,
    TableOptionError,
    WrongPasswordError,
)
from app.tables.items import CatalogItem
from app.tables.model_picker import ModelPicker
from app.tables.models import (
    GameTable,
    TableInjury,
    TableItem,
    TableMember,
    TableQuest,
    TableRoll,
    TableSheet,
    TableWorn,
)
from app.tables.retirement_watch import RetirementWatch
from app.tables.schemas import (
    CatalogItemOut,
    CharacterOut,
    CharacterUpdate,
    CreditWaitUpdate,
    CurrencyOut,
    FallenOut,
    HostTransfer,
    InjuryOut,
    ItemOut,
    JoinRequest,
    LobbyJoinRequest,
    MapOut,
    MemberOut,
    NarrationModelOut,
    NarrationModelsOut,
    NarrationModelUpdate,
    NarrationStyleUpdate,
    NextPriceOut,
    PlaceItemOut,
    PlaceOut,
    PregenChoice,
    QuestOut,
    ReferencesUpdate,
    RollOut,
    RoundTimeLimitUpdate,
    RouteCrossOut,
    RouteOut,
    SheetOut,
    StepPriceOut,
    TableCreate,
    TableDetail,
    TablePage,
    TableSummary,
    WearRequest,
    WhisperNoticeUpdate,
    WornOut,
)

router = APIRouter(prefix='/tables', tags=['tables'])


def get_model_picker(prices: Prices, now: Now) -> ModelPicker:
    """방장이 고른 서술 모델을 확인할 것. 가격 목록은 모델을 골랐을 때만 묻는다(app/tables/model_picker.py)."""
    return ModelPicker(prices=prices, now=now)


Picker = Annotated[ModelPicker, Depends(get_model_picker)]


def get_retirement_watch(request: Request) -> RetirementWatch:
    """서술 모델의 은퇴를 지켜보는 작업. 앱에 하나 꽂혀 있다(app/main.py)."""
    return request.app.state.retirement_watch


Watch = Annotated[RetirementWatch, Depends(get_retirement_watch)]


def to_next_out(change: Change | None) -> NextPriceOut | None:
    """예약된 바뀜을 응답으로. 판매를 멈추는 예약이면 값과 등급이 null 이다."""
    if change is None:
        return None
    credits = change.sale.credits if change.sale else None
    tier = change.sale.tier if change.sale else None
    promo = change.sale.promo if change.sale else False
    return NextPriceOut(credits=credits, tier=tier, promo=promo, effective_at=change.effective_at)


def to_step_out(sale: StepPrice) -> StepPriceOut:
    """모델의 단계 하나와 그 값을 응답으로."""
    return StepPriceOut(
        input_step=sale.steps.input,
        output_step=sale.steps.output,
        input_tokens=input_tokens(sale.steps),
        output_tokens=output_tokens(sale.steps),
        credits=sale.credits,
        tier=sale.tier,
        promo=sale.promo,
        next=to_next_out(sale.next),
    )


def to_model_out(found: OfferedModel) -> NarrationModelOut:
    """고를 수 있는 모델 하나를 응답으로."""
    return NarrationModelOut(
        slug=found.slug,
        display_name=found.display_name,
        vendor=found.vendor,
        grade=found.grade,
        credits=found.credits,
        tier=found.tier,
        promo=found.promo,
        next=to_next_out(found.next),
        retires_on=found.retires_on,
        options=[to_step_out(sale) for sale in found.options],
    )


async def handle_prices_unavailable(request: Request, error: PriceListUnavailable) -> JSONResponse:
    """
    가격 목록을 받지 못했고 받아 둔 것도 없으면 503 이다. 값을 모르는 모델을 내주지 않는다.

    까닭(unreachable, status_401 …)은 싣지 않는다. 결제 서버의 사정이다. 서버 로그에는 남는다.
    """
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={'detail': '모델의 값을 받아 오지 못했습니다. 잠시 뒤에 다시 시도해 주세요.'},
    )


def to_summary(table: GameTable) -> TableSummary:
    """테이블을 목록용 응답으로 바꾼다."""
    return TableSummary(
        id=table.id,
        scenario_id=table.scenario_id,
        title=table.title,
        status=table.status,
        rating=table.rating,
        capacity=table.capacity,
        member_count=len(table.members),
        host_id=table.host_id,
        is_public=table.is_public,
        has_password=table.password_hash is not None,
        narration_style=table.narration_style,
        round_time_limit=table.round_time_limit,
        narration_model=table.narration_model,
        input_step=table.input_step,
        output_step=table.output_step,
        credit_wait_seconds=table.credit_wait_seconds,
        remove_short_payers=table.remove_short_payers,
        whisper_notice=table.whisper_notice,
        references_enabled=table.references_enabled,
        created_at=table.created_at,
    )


def to_item(item: TableItem, catalog: dict[uuid.UUID, CatalogItem]) -> ItemOut:
    """
    가진 물건 한 가지를 응답으로 바꾼다. 이름과 종류는 판에서 찾는다.

    소지품은 판의 물건만 가리킨다(판에 없는 물건은 줄 수 없다). 판은 바뀌지 않으므로 늘 찾는다.
    """
    found = catalog[item.entry_id]
    return ItemOut(entry_id=item.entry_id, name=found.name, kind=found.kind, rarity=found.rarity, count=item.count)


def to_quest(quest: TableQuest, catalog: dict[uuid.UUID, quests.CatalogQuest]) -> QuestOut:
    """퀘스트 하나를 응답으로 바꾼다. 이름은 판에서 찾는다. 기한이 있으면 끝나는 시각을 게임 안의 시각으로 푼다."""
    due_at = None if quest.due_at is None else clock.as_document(quest.due_at)
    return QuestOut(entry_id=quest.entry_id, name=catalog[quest.entry_id].name, status=quest.status, due_at=due_at)


def to_catalog(catalog: dict[uuid.UUID, CatalogItem]) -> list[CatalogItemOut]:
    """판의 물건들을 응답으로 바꾼다."""
    return [
        CatalogItemOut(
            entry_id=item.entry_id,
            name=item.name,
            kind=item.kind,
            heals=item.heals,
            rarity=item.rarity,
            price=item.price,
            slots=list(item.slots),
            slot_count=item.slot_count,
            attack=item.attack,
            defense=item.defense,
            guard=item.guard,
            ap=item.ap,
            ward=item.ward,
        )
        for item in catalog.values()
    ]


def to_currency(currency: CurrencySnapshot | None) -> CurrencyOut | None:
    """판의 화폐를 응답으로 바꾼다. 시작 돈은 싣지 않는다. 이미 받았다. 화폐가 없으면 None."""
    if currency is None:
        return None
    return CurrencyOut(name=currency.name, unit=currency.unit, sell_percent=currency.sell_percent)


def to_injury(row: TableInjury) -> InjuryOut:
    """입고 있는 부상 하나를 응답으로. 오래 가는 것이면 나을 시각을 게임 안의 시각으로 푼다."""
    heals_at = None if row.heals_at is None else clock.as_document(row.heals_at)
    return InjuryOut(
        injury=row.injury, round=row.round_number, ends_after_round=row.ends_after_round, heals_at=heals_at
    )


def to_worn(row: TableWorn, catalog: dict[uuid.UUID, CatalogItem]) -> WornOut:
    """착용 하나를 응답으로 바꾼다. 이름은 판에서 찾는다."""
    return WornOut(entry_id=row.entry_id, name=catalog[row.entry_id].name, slots=list(row.slots))


def to_sheet(sheet: TableSheet | None, catalog: dict[uuid.UUID, CatalogItem], ruleset: Ruleset) -> SheetOut | None:
    """
    시트를 응답으로 바꾼다. 아직 받지 않았으면 None. 소지품의 이름은 판의 물건(catalog)에서 찾는다.

    착용은 규칙(ruleset)의 칸의 차례로 놓는다.
    """
    if sheet is None:
        return None
    return SheetOut(
        number=sheet.number,
        abilities=sheet.abilities,
        max_hp=sheet.max_hp,
        hp=sheet.hp,
        death_successes=sheet.death_successes,
        death_failures=sheet.death_failures,
        dead=sheet.died_at is not None,
        injuries=[to_injury(row) for row in injuries.active(sheet.injuries)],
        items=[to_item(item, catalog) for item in items.in_catalog_order(sheet.items, catalog)],
        money=sheet.money,
        worn=[to_worn(row, catalog) for row in equipment.in_slot_order(sheet.worn, ruleset)],
        place_id=sheet.place_id,
    )


def to_place_items(table: GameTable, place_id: uuid.UUID, catalog: dict[uuid.UUID, CatalogItem]) -> list[PlaceItemOut]:
    """
    그 장소에 보이게 놓인 물건들을 응답으로 바꾼다. 서 본 적 없는 장소면 빈 목록이다.

    숨긴 물건은 싣지 않는다(app/tables/place_items.py).
    """
    if place_id not in place_items.seen_places(table):
        return []
    return [
        PlaceItemOut(entry_id=pile.entry_id, name=catalog[pile.entry_id].name, count=pile.count)
        for pile in place_items.piles_at(table, place_id)
    ]


def to_map(table: GameTable, snapshot: Snapshot, catalog: dict[uuid.UUID, CatalogItem]) -> MapOut | None:
    """
    테이블이 아는 맵을 응답으로 바꾼다. 맵이 없는 판이면 None. 아는 것만 싣는다(app/tables/places.py).

    catalog 는 판의 물건들이다. 장소에 놓인 물건의 이름을 찾는다.
    """
    known = places.known_map(snapshot, places.knowledge(table))
    if known is None:
        return None
    return MapOut(
        places=[
            PlaceOut(
                entry_id=place.id,
                name=place.name,
                items=to_place_items(table, place.id, catalog),
                cover=cover_at(snapshot, place.id),
            )
            for place in known.places
        ],
        routes=[to_route(table, snapshot, route) for route in known.routes],
    )


def to_route(table: GameTable, snapshot: Snapshot, route: RouteSnapshot) -> RouteOut:
    """아는 길 하나를 응답으로 바꾼다. 문(자물쇠, 빗장)은 이 테이블의 지금 상태, 판정들은 판의 것이다(#281)."""
    locked = route_locks.is_locked(table, route) if route.lock is not None else None
    barred = route_locks.is_barred(table, route) if route.bar is not None else None
    pick = route.lock.pick if route.lock is not None else None
    return RouteOut(
        from_place=route.from_place,
        to_place=route.to_place,
        two_way=route.two_way,
        travel_minutes=route.travel_minutes,
        locked=locked,
        cross=to_cross(snapshot, route.cross),
        barred=barred,
        bar_side=route.bar.side if route.bar is not None else None,
        broken=route_locks.is_broken(table, route),
        pick=to_cross(snapshot, pick),
        force=to_cross(snapshot, route.force),
    )


def to_cross(snapshot: Snapshot, terms: CrossSnapshot | PickSnapshot | ForceSnapshot | None) -> RouteCrossOut | None:
    """길에 적힌 판정을 응답으로 바꾼다. 난이도를 비웠으면 규칙의 기본 난이도의 이름표다. 없으면 None."""
    if terms is None:
        return None
    difficulty = find_difficulty(snapshot.rulebook.rules, terms.difficulty)
    return RouteCrossOut(ability=terms.ability, difficulty=difficulty.key)


def to_roll(roll: TableRoll | None) -> RollOut | None:
    """굴린 것을 응답으로 바꾼다. 굴린 적이 없으면 None."""
    if roll is None:
        return None
    return RollOut(
        dice=roll.dice,
        scores=roll.scores,
        times_rolled=roll.times_rolled,
        character_number=roll.character_number,
        reroll_granted=roll.reroll_granted,
    )


def to_fallen(sheet: TableSheet) -> FallenOut:
    """떠난 캐릭터의 시트를 응답으로 바꾼다."""
    return FallenOut(
        number=sheet.number,
        character_name=sheet.character_name,
        pregen_index=sheet.pregen_index,
        abilities=sheet.abilities,
        max_hp=sheet.max_hp,
    )


def to_member(
    table: GameTable, member: TableMember, catalog: dict[uuid.UUID, CatalogItem], ruleset: Ruleset
) -> MemberOut:
    """앉은 사람 하나를 응답으로 바꾼다."""
    character = None
    if member.character_name is not None:
        character = CharacterOut(name=member.character_name, description=member.character_description)
    return MemberOut(
        user_id=member.user_id,
        is_host=member.user_id == table.host_id,
        character=character,
        character_mode=member.character_mode,
        pregen_index=member.pregen_index,
        roll=to_roll(sheets.find_roll(table, member.user_id)),
        abilities=member.abilities,
        sheet=to_sheet(member.sheet, catalog, ruleset),
        fallen=[to_fallen(sheet) for sheet in member.fallen],
        joined_at=member.joined_at,
    )


def find_pregen_holders(table: GameTable) -> dict[int, tuple[uuid.UUID, bool]]:
    """
    프리젠마다 가져간 사람과 그 캐릭터가 죽었는지를 찾는다. 프리젠의 번호에서 (사람, 죽었는가) 로 간다.

    시작 전에는 자리에 적힌 것을 본다. 시작한 뒤에는 시트에도 적혀 있다. 떠난 캐릭터의 프리젠은 시트에만 남아 있다.
    """
    holders = {
        member.pregen_index: (member.user_id, False) for member in table.members if member.pregen_index is not None
    }
    for member in table.members:
        for sheet in member.sheets:
            if sheet.pregen_index is not None:
                holders[sheet.pregen_index] = (member.user_id, sheet.died_at is not None)
    return holders


def to_pregen_choices(table: GameTable, snapshot: Snapshot) -> list[PregenChoice]:
    """프리젠마다 누가 가져갔는지와 그 캐릭터가 죽었는지를 붙여 응답으로 바꾼다."""
    holders = find_pregen_holders(table)
    choices = []
    for index, pregen in enumerate(snapshot.pregens):
        taken_by, dead = holders.get(index, (None, False))
        choices.append(
            PregenChoice(
                name=pregen.name, description=pregen.description, sheet=pregen.sheet, taken_by=taken_by, dead=dead
            )
        )
    return choices


def to_player_made_hp(table: GameTable, snapshot: Snapshot) -> PlayerMadeHp | None:
    """최대 HP 를 구하는 값을 응답으로 바꾼다. 플레이어가 능력치를 정하는 방식을 허용하지 않는 테이블이면 None."""
    allows_player_made = any(mode in PLAYER_MADE_MODES for mode in table.character_modes)
    if not allows_player_made or snapshot.player_made_hp is None:
        return None
    return PlayerMadeHp(**snapshot.player_made_hp.model_dump())


def can_grant_rerolls(table: GameTable, snapshot: Snapshot) -> bool:
    """방장이 "한 번 더 굴리기"를 줄 수 있는 테이블인가. 제작자가 허락했고, 그 방식을 쓰는 테이블이어야 한다."""
    return snapshot.reroll_allowed and CharacterMode.ROLLED in table.character_modes


def to_detail(table: GameTable, viewer_id: uuid.UUID) -> TableDetail:
    """
    테이블을 참가자에게 보여 주는 응답으로 바꾼다. 여기 적은 칸만 나간다.

    viewer_id 는 보는 사람이다. 초대 코드는 방장에게만 싣는다. 숨긴 퀘스트는 아무에게도 싣지 않는다.
    """
    snapshot = read_snapshot(table.content)
    catalog = items.catalog(snapshot)
    quest_catalog = quests.catalog(snapshot)
    return TableDetail(
        **to_summary(table).model_dump(),
        opening=snapshot.openings[table.opening_index],
        recommended_players=RecommendedPlayers(**snapshot.recommended_players.model_dump()),
        rules=snapshot.rulebook.rules,
        character_modes=table.character_modes,
        default_sheet=snapshot.default_sheet if CharacterMode.CUSTOM in table.character_modes else None,
        player_made_hp=to_player_made_hp(table, snapshot),
        reroll_allowed=can_grant_rerolls(table, snapshot),
        recommended_narration_style=snapshot.narration_style,
        pregens=to_pregen_choices(table, snapshot),
        items=to_catalog(catalog),
        currency=to_currency(snapshot.currency),
        quests=[to_quest(quest, quest_catalog) for quest in quests.visible_quests(table, quest_catalog)],
        map=to_map(table, snapshot, catalog),
        clock=to_clock(table),
        members=[to_member(table, member, catalog, snapshot.rulebook.rules) for member in table.members],
        invite_code=table.invite_code if viewer_id == table.host_id else None,
        started_at=table.started_at,
        ended_at=table.ended_at,
    )


# --- 서비스의 예외를 응답으로 바꾼다. 앱에 한 번 등록한다(app/main.py) ---


async def handle_table_not_found(request: Request, error: TableNotFoundError) -> JSONResponse:
    """
    "그런 테이블이 없다"는 404 다.

    앉지 않은 사람에게도, 초대 코드가 틀린 사람에게도 404 다. 403 을 주면 그 테이블이 있다는 것이 드러난다.
    """
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '테이블을 찾을 수 없습니다.'})


async def handle_member_not_found(request: Request, error: MemberNotFoundError) -> JSONResponse:
    """ "그 사람은 이 테이블에 없다"는 404 다."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '참가자를 찾을 수 없습니다.'})


async def handle_not_host(request: Request, error: NotHostError) -> JSONResponse:
    """
    "방장만 할 수 있다"는 403 이다.

    여기서는 403 을 써도 된다. 이 응답을 받는 사람은 테이블에 앉아 있어서, 테이블이 있다는 것을 이미 안다.
    """
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={'detail': '방장만 할 수 있습니다.'})


async def handle_wrong_password(request: Request, error: WrongPasswordError) -> JSONResponse:
    """
    "비밀번호가 틀렸다"는 403 이다.

    404 가 아니다. 로비에 보이는 테이블이라 있다는 것은 누구나 안다.
    """
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={'detail': '비밀번호가 맞지 않습니다.'})


async def handle_table_conflict(request: Request, error: TableConflictError) -> JSONResponse:
    """ "테이블의 지금 상태와 부딪힌다"는 409 다. 이유를 reason 에 싣는다. 화면이 이 값으로 안내를 고른다."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '테이블의 지금 상태에서는 할 수 없습니다.', 'reason': error.reason},
    )


async def handle_table_option(request: Request, error: TableOptionError) -> JSONResponse:
    """ "고른 번호가 판에 없다"는 422 다. 주소는 맞고, 본문에 적은 값이 틀렸다."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': f'{error.field} 에 고를 수 없는 값이 있습니다.'},
    )


# --- 만들기, 들어가기, 읽기 ---


@router.post('', response_model=TableDetail, status_code=status.HTTP_201_CREATED)
async def create_table(data: TableCreate, user: CurrentUser, session: Session, picker: Picker) -> TableDetail:
    """
    테이블을 만든다. 만든 사람이 방장이 되어 앉는다.

    서술 모델은 고른 것, 아니면 시나리오의 추천 모델, 쓸 수 없으면 같은 회사의 대체 모델이다.
    셋 다 없으면 422(narration_model)다. 방장이 모델을 골라 다시 보낸다.
    """
    table = await service.create_table(session, user, data, picker)
    return to_detail(table, user.user_id)


@router.post('/join', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def join_table(data: JoinRequest, user: CurrentUser, session: Session) -> TableDetail:
    """초대 코드로 테이블에 들어가 앉는다."""
    table = await service.join_table(session, user, data)
    return to_detail(table, user.user_id)


@router.get('', response_model=TablePage, status_code=status.HTTP_200_OK)
async def list_tables(user: CurrentUser, session: Session, paging: Paging) -> TablePage:
    """내가 앉아 있는 테이블을 최근에 만든 것부터 돌려준다."""
    tables, total = await service.list_tables(session, user.user_id, paging.limit, paging.offset)
    return TablePage(items=[to_summary(table) for table in tables], total=total)


# 로비를 시나리오로 거르는 값. 주소의 ?scenario_id=.. 에서 읽는다
ScenarioFilter = Annotated[uuid.UUID | None, Query()]


# /narration-models, /lobby 를 /{table_id} 보다 먼저 적는다. 먼저 적은 주소가 먼저 맞춰진다
@router.get('/narration-models', response_model=NarrationModelsOut, status_code=status.HTTP_200_OK)
async def list_narration_models(user: CurrentUser, session: Session, prices: Prices, now: Now) -> NarrationModelsOut:
    """
    테이블의 서술 모델로 고를 수 있는 모델들과 1인 1라운드의 값. 로그인한 사람에게만 보인다(가격 수집 막기).

    모델 목록에서 켜져 있고 결제 서버가 지금 파는 모델만 나온다. 값이 바뀌는 예약이 있으면 next 에 싣는다.
    """
    offering = await offers.list_offered(session, prices, now)
    return NarrationModelsOut(free=offering.free, models=[to_model_out(found) for found in offering.models])


@router.get('/lobby', response_model=TablePage, status_code=status.HTTP_200_OK)
async def list_lobby(
    user: CurrentUser, session: Session, paging: Paging, scenario_id: ScenarioFilter = None
) -> TablePage:
    """로비. 들어갈 수 있는 테이블을 최근에 만든 것부터 돌려준다. 모집 중이고 자리가 남은 것만 나온다."""
    tables, total = await service.list_lobby(session, user, scenario_id, paging.limit, paging.offset)
    return TablePage(items=[to_summary(table) for table in tables], total=total)


@router.get('/{table_id}', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def read_table(table_id: uuid.UUID, user: CurrentUser, session: Session) -> TableDetail:
    """내가 앉아 있는 테이블 하나를 돌려준다."""
    table = await service.get_table(session, user.user_id, table_id)
    return to_detail(table, user.user_id)


@router.post('/{table_id}/join', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def join_public_table(
    table_id: uuid.UUID, data: LobbyJoinRequest, user: CurrentUser, session: Session, limiting: Limited
) -> TableDetail:
    """
    로비에 보이는 테이블에 들어가 앉는다. 비밀번호가 걸려 있으면 비밀번호를 보낸다.

    비밀번호를 너무 많이 틀리면 한동안 429 다(app/tables/password_attempts.py).
    """
    table = await service.join_public_table(session, user, table_id, data, limiting)
    return to_detail(table, user.user_id)


# --- 참가자가 하는 일 ---


@router.put('/{table_id}/character', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def set_character(table_id: uuid.UUID, data: CharacterUpdate, user: CurrentUser, session: Session) -> TableDetail:
    """내 캐릭터를 정한다. 직접 만들거나 프리젠을 가져온다. 모집 중에만 된다."""
    table = await service.set_character(session, user.user_id, table_id, data)
    return to_detail(table, user.user_id)


# 201: 새 캐릭터가 생겼다는 뜻이다. PUT 과 나눈 이유: PUT 은 같은 요청을 몇 번 보내도 결과가 같다.
# 이것은 한 번만 된다. 새 캐릭터가 들어오면 그 캐릭터는 살아 있고, 살아 있는 동안에는 다시 들일 수 없다
@router.post('/{table_id}/character', response_model=TableDetail, status_code=status.HTTP_201_CREATED)
async def bring_in_character(
    table_id: uuid.UUID, data: CharacterUpdate, user: CurrentUser, session: Session
) -> TableDetail:
    """
    죽은 내 캐릭터의 뒤를 이을 새 캐릭터를 들인다. 진행 중인 테이블에서, 내 캐릭터가 죽었을 때만 된다.

    받는 값은 캐릭터를 정할 때와 같다. 새 캐릭터는 시트를 바로 받고, 다음 라운드부터 선언을 낸다.
    주사위로 정하는 방식이면 먼저 새로 굴린다(POST .../character/roll).
    """
    table = await replacements.bring_in_character(session, user.user_id, table_id, data)
    return to_detail(table, user.user_id)


@router.delete('/{table_id}/character', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def give_up_character(table_id: uuid.UUID, user: CurrentUser, session: Session) -> TableDetail:
    """
    쓰러진 내 캐릭터를 스스로 보낸다. 캐릭터가 죽는다. 되돌릴 수 없다.

    진행 중인 테이블에서, 캐릭터가 쓰러져 있을 때만 된다. 죽음의 굴림을 기다리지 않고 새 캐릭터로 넘어가려는 때 쓴다.
    라운드를 닫으러 보지 않는다. 쓰러진 사람은 원래 라운드가 기다리지 않으므로, 보내도 기다릴 사람이 줄지 않는다.
    """
    table = await deaths.give_up_character(session, user.user_id, table_id)
    return to_detail(table, user.user_id)


@router.post('/{table_id}/character/persona', response_model=PersonaOut, status_code=status.HTTP_201_CREATED)
async def keep_character(table_id: uuid.UUID, user: CurrentUser, session: Session) -> PersonaOut:
    """
    이 테이블의 내 캐릭터를 내 보관함에 저장한다. 이름, 설명, 시작할 때의 능력치를 저장한다.

    프리젠은 저장하지 못한다. 저장한 것은 사본이라, 그 뒤에 테이블에서 바뀐 것은 보관함으로 오지 않는다.
    """
    persona = await saving.save_character(session, user.user_id, table_id)
    return to_persona(persona)


@router.post('/{table_id}/character/roll', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def roll_abilities(table_id: uuid.UUID, user: CurrentUser, session: Session, dice: Rolling) -> TableDetail:
    """
    내 능력치의 점수를 주사위로 굴린다. 본문이 없다. 굴리는 것은 서버다.

    캐릭터 하나에 한 번만 된다. 굴린 점수는 응답의 members[].roll 에 있다. 그것을 능력치에 놓아 캐릭터를 정한다.
    진행 중에는 캐릭터가 죽은 사람이 새 캐릭터를 위해 굴린다.
    """
    table = await rolls.roll_abilities(session, user.user_id, table_id, dice)
    return to_detail(table, user.user_id)


# /members/me 를 /members/{user_id} 보다 먼저 적는다. 먼저 적은 주소가 먼저 맞춰진다
@router.delete('/{table_id}/members/me', status_code=status.HTTP_204_NO_CONTENT)
async def leave_table(table_id: uuid.UUID, user: CurrentUser, session: Session, closer: Closing, dice: Rolling) -> None:
    """
    테이블에서 나간다. 방장이 나가면 가장 먼저 들어온 사람이 방장이 된다.

    진행 중이면, 나간 사람만 내지 않았던 라운드를 닫기 시작한다. 남은 사람이 기다리지 않게 한다.
    """
    await service.leave_table(session, user.user_id, table_id)
    await round_service.close_when_ready(session, table_id, closer, dice)


# --- 방장이 하는 일 ---


@router.delete('/{table_id}/members/{user_id}', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def kick_member(
    table_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, session: Session, closer: Closing, dice: Rolling
) -> TableDetail:
    """
    참가자를 내보낸다. 초대 코드가 새로 만들어진다. 응답에 새 코드가 실린다.

    진행 중이면, 내보낸 사람만 내지 않았던 라운드를 닫기 시작한다.
    """
    table = await service.kick_member(session, user.user_id, table_id, user_id)
    await round_service.close_when_ready(session, table_id, closer, dice)
    return to_detail(table, user.user_id)


@router.put('/{table_id}/equipment', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def wear_equipment(table_id: uuid.UUID, data: WearRequest, user: CurrentUser, session: Session) -> TableDetail:
    """
    자기 캐릭터가 가진 물건 하나를 장비의 칸들에 끼운다(#276). 찬 칸의 것은 벗겨진다. 라운드의 행동이 아니다.

    선언을 받는 중에만 된다(닫는 중이면 409 round_closing). 쓰러졌거나 죽었으면 409.
    착용하지 않는 물건이나 판에 없는 물건이면 422(entry_id), 칸이 맞지 않으면 422(slots),
    가지고 있지 않으면 409(not_enough_items). 모두에게 이벤트(equipment_changed)가 간다.
    """
    table = await wearing.wear_item(session, user.user_id, table_id, data.entry_id, data.slots)
    return to_detail(table, user.user_id)


@router.delete('/{table_id}/equipment/{slot}', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def take_off_equipment(table_id: uuid.UUID, slot: str, user: CurrentUser, session: Session) -> TableDetail:
    """
    자기 캐릭터의 그 칸을 비운다(#276). 그 칸을 차지한 착용이 통째로 빠진다. 비어 있으면 그대로 돌려준다.

    선언을 받는 중에만 된다(닫는 중이면 409 round_closing). 쓰러졌거나 죽었으면 409.
    """
    table = await wearing.take_off_slot(session, user.user_id, table_id, slot)
    return to_detail(table, user.user_id)


@router.post('/{table_id}/members/{user_id}/reroll', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def grant_reroll(table_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, session: Session) -> TableDetail:
    """참가자 한 사람에게 "한 번 더 굴리기"를 준다. 시나리오의 제작자가 허락한 테이블에서만 된다."""
    table = await rolls.grant_reroll(session, user.user_id, table_id, user_id)
    return to_detail(table, user.user_id)


@router.put('/{table_id}/host', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def transfer_host(table_id: uuid.UUID, data: HostTransfer, user: CurrentUser, session: Session) -> TableDetail:
    """방장을 다른 참가자에게 넘긴다."""
    table = await service.transfer_host(session, user.user_id, table_id, data)
    return to_detail(table, user.user_id)


@router.put('/{table_id}/narration-style', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def change_narration_style(
    table_id: uuid.UUID, data: NarrationStyleUpdate, user: CurrentUser, session: Session
) -> TableDetail:
    """GM 의 서술 문체를 바꾼다. 방장만 한다. 진행 중에도 되고, 다음 서술부터 쓴다. null 이면 시나리오의 추천 문체로."""
    table = await styles.change_narration_style(session, user.user_id, table_id, data)
    return to_detail(table, user.user_id)


@router.put('/{table_id}/round-time-limit', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def change_round_time_limit(
    table_id: uuid.UUID, data: RoundTimeLimitUpdate, user: CurrentUser, session: Session
) -> TableDetail:
    """
    라운드의 시간 제한(초)을 바꾼다. 방장만 한다. null 이면 시간 제한을 없앤다.

    진행 중에도 된다. 바꾼 값은 다음 라운드부터 쓴다. 지금 열린 라운드의 마감은 그대로다.
    """
    table = await time_limits.change_round_time_limit(session, user.user_id, table_id, data)
    return to_detail(table, user.user_id)


@router.put('/{table_id}/narration-model', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def change_narration_model(
    table_id: uuid.UUID, data: NarrationModelUpdate, user: CurrentUser, session: Session, picker: Picker
) -> TableDetail:
    """
    서술 모델을 바꾼다. 방장만 한다. 고를 수 있는 모델만 된다(GET /tables/narration-models).

    진행 중에도 된다. 바꾼 값은 다음 라운드부터 쓴다.
    다만 아직 서술하지 않은 지금 라운드(선언을 받는 중이거나 서술이 실패해 멈춤)는 함께 바꾸고 새 값으로 다시 건다.
    """
    table = await narration_models.change_narration_model(session, user.user_id, table_id, data, picker)
    return to_detail(table, user.user_id)


@router.put('/{table_id}/credit-wait', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def change_credit_wait(
    table_id: uuid.UUID, data: CreditWaitUpdate, user: CurrentUser, session: Session
) -> TableDetail:
    """
    크레딧이 모자란 사람을 기다리는 시간(초)과, 지나면 그 사람을 자리에서 빼는지를 바꾼다. 방장만 한다.

    진행 중에도 된다. 지금 기다리는 라운드에도 바로 쓴다.
    """
    table = await credit_waits.change_credit_wait(session, user.user_id, table_id, data)
    return to_detail(table, user.user_id)


@router.put('/{table_id}/whisper-notice', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def change_whisper_notice(
    table_id: uuid.UUID, data: WhisperNoticeUpdate, user: CurrentUser, session: Session
) -> TableDetail:
    """
    쪽지를 보낸 사실을 모두에게 알릴지 바꾼다. 방장만 한다.

    켜면 쪽지를 보낼 때마다 "누가 누구에게 보냈다"가 이벤트(whisper_sent)로 간다. 글은 가지 않는다.
    진행 중에도 된다. 바꾼 뒤에 보내는 쪽지부터 따른다.
    """
    table = await whisper_notices.change_whisper_notice(session, user.user_id, table_id, data)
    return to_detail(table, user.user_id)


@router.put('/{table_id}/references', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def change_references(
    table_id: uuid.UUID, data: ReferencesUpdate, user: CurrentUser, session: Session
) -> TableDetail:
    """
    서술에 참고 자료(SRD 같은 바깥 자료)를 넣을지 바꾼다. 방장만 한다. 모집 중에만 된다(시작하면 고정이다).

    켜려면 판의 세계관이 허용해야 한다. 아니면 422 다.
    """
    table = await references.change_references(session, user.user_id, table_id, data)
    return to_detail(table, user.user_id)


@router.post('/{table_id}/start', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def start_table(
    table_id: uuid.UUID, user: CurrentUser, session: Session, watch: Watch, prices: Prices
) -> TableDetail:
    """
    테이블을 시작한다. 모든 참가자가 캐릭터를 만들어 둬야 한다.

    첫 라운드에 1인 1라운드의 값을 알린다(app/rounds/round_price.py).
    첫 라운드를 연 뒤 서술 모델의 은퇴를 본다(app/tables/retirement_watch.py). 은퇴했으면 바뀐 모델로 답한다.
    """
    await service.start_table(session, user.user_id, table_id, prices)
    await watch.after_round_opened(table_id)
    table = await repository.reload_table(session, table_id)
    return to_detail(table, user.user_id)


@router.post('/{table_id}/end', response_model=TableDetail, status_code=status.HTTP_200_OK)
async def end_table(table_id: uuid.UUID, user: CurrentUser, session: Session) -> TableDetail:
    """테이블을 끝낸다."""
    table = await service.end_table(session, user.user_id, table_id)
    return to_detail(table, user.user_id)
