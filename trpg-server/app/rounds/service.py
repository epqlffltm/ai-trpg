# trpg-server/app/rounds/service.py

"""
라운드의 일(유스케이스). 라운드를 읽고, 선언을 받고, 라운드를 닫는다.

HTTP 를 모른다. SQL 을 모른다. 어디까지를 한 묶음으로 저장할지(커밋)는 여기서 정한다.
판단과 계산은 작은 모듈에 있고, 여기는 그것들을 차례로 부르고 저장한다.
  - app/rounds/errors.py: 거절되는 까닭들
  - app/rounds/state.py: 지금 상태를 보는 판단
  - app/rounds/acceptance.py: 선언을 받기
  - app/rounds/judging.py: 닫을 때의 판정(checks.py 판정, treatments.py 치료, effects.py 함께 쓰는 것)
  - app/rounds/moves.py: 서술자에게 줄 각자 한 일
  - app/rounds/records.py: 이벤트 적기

테이블의 규칙을 그대로 따른다(app/tables/service.py).
  - 라운드는 테이블에 앉은 사람만 본다.
  - 바꾸는 일(선언, 닫기)은 테이블의 행을 잠그고 한다. 라운드를 따로 잠그지 않는다.
    한 테이블의 일은 테이블 하나의 잠금으로 줄을 세운다. 잠금이 둘이면 서로를 기다리며 멈출 수 있다.

라운드가 닫히는 길은 둘이다. 앉은 사람이 모두 선언을 냈을 때 저절로, 또는 방장이 닫을 때.

닫는 일은 둘로 나뉜다. 사이에 GM 의 서술이 있고, 서술은 오래 걸린다(AI 를 부르면 몇 초에서 십몇 초).
  1. 닫기 시작(begin_closing): 테이블을 잠그고, 선언을 마감하고, 행동을 판정하고, 저장한다.
     라운드는 "닫는 중"이 된다. 판정과 각자 한 일, 문체는 이때 한 번만 정해 굳힌다.
  2. 서술: 잠금도 DB 연결도 없이, 요청과 따로 도는 작업이 서술자를 부른다(app/rounds/closing.py).
  3. 닫기 마무리(finish_closing): 다시 잠그고, 서술을 장면으로 하는 다음 라운드를 열고, 저장한다.
잠금을 쥔 채로 서술을 기다리지 않는다. 기다리면 그동안 이 테이블의 채팅과 나가기가 전부 멈춘다.
닫기 시작한 라운드는 저장한 뒤에 까닭(reason)마다 센다(rounds_closed_total). 되돌린 것은 세지 않는다.

서술을 맡은 작업은 사라질 수 있다(서버가 꺼짐, 서술자가 실패함). 그러면 라운드가 닫는 중에 머문다.
맡긴 지 한참 지난 라운드는 방장이 닫기를 다시 눌러 서술을 다시 맡긴다(is_stalled).

서술을 맡길 때마다 닫기 시작한 시각(closing_at)을 새로 적는다. 이 시각이 "몇 번째로 맡긴 서술인가"의 표다.
서술을 맡은 작업은 맡을 때의 시각을 들고 다니고, 라운드를 바꾸기 전에 잠금 안에서 그 시각이 아직 같은지 본다.
다시 맡긴 뒤에 늦게 끝난 옛 작업은 시각이 달라 아무것도 바꾸지 못한다. 실패를 적지도, 라운드를 닫지도 못한다.
칸을 따로 두지 않는다. 시각은 테이블을 잠근 채로만 고치고, 다시 맡기려면 실패가 적혔거나 한참 지나야 해서
같은 시각이 두 번 적히지 않는다.

닫기 시작하기 바로 전에 게임 상태를 찍어 둔다(start_closing, app/rounds/snapshots.py). 방장이 바로 앞 라운드를
되돌리면 그 상태로 덮고 같은 번호의 라운드를 다시 연다(revert_round, app/rounds/reverting.py, #288).

죽은 캐릭터의 플레이어는 선언을 낼 수 없다. 새 캐릭터가 있어야 한다.
새 캐릭터를 들인 라운드에는 선언을 내지 않는다. 다음 라운드부터 낸다.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import charges
from app.billing import repository as billing_repository
from app.billing.models import NarrationCharge
from app.billing.price_list import FREE_PRICES, PriceList
from app.calendar import state as calendar
from app.catalog.steps import steps_of
from app.core.config import BILLING_BUDGET_SECONDS, NARRATION_BUDGET_SECONDS
from app.engine.dice import Dice
from app.engine.ruleset import Ruleset
from app.events import recorder
from app.events import repository as event_repository
from app.events.models import EventType, TableEvent
from app.memory import repository as memory_repository
from app.observability.metrics import record_round_closed
from app.portraits.seats import entry_pictures
from app.rounds import (
    achievements,
    chapters,
    deadlines,
    happening_traps,
    happenings,
    improvised,
    injury_escapes,
    injury_ticks,
    monster_roams,
    monster_xp,
    narration_request,
    opener,
    quest_goals,
    repository,
    resource_rounds,
    rests,
    reverting,
    snapshots,
    turn_order,
    waits,
    wanders,
)
from app.rounds.acceptance import accept_action, put_declaration
from app.rounds.cast import Scene, cast_of, labels_of
from app.rounds.errors import Conflict, RoundConflictError, RoundNotFoundError
from app.rounds.judging import expire_injuries, find_dying, roll_checks, roll_death_saves
from app.rounds.models import CloseReason, Round, RoundStatus
from app.rounds.monster_scene import occupied_places, scene_monsters
from app.rounds.move_lines import round_lines
from app.rounds.moves import build_moves, frozen_moves, frozen_style, place_names, to_monster_notes, to_people
from app.rounds.narrator import NarrationRequest
from app.rounds.prompt import history_rounds
from app.rounds.records import record_actions, record_death_saves, record_injury_endings, record_recoveries
from app.rounds.round_price import price_of
from app.rounds.schemas import DeclarationUpdate
from app.rounds.state import (
    find_arrival,
    is_awaited,
    is_overdue,
    is_ready,
    require_open,
    require_playing,
    require_started,
    rules_of,
    waiting_for,
)
from app.tables import items, sheets
from app.tables import repository as table_repository
from app.tables import service as tables
from app.tables import state as table_state
from app.tables.content import snapshot_of
from app.tables.items import CatalogItem
from app.tables.models import GameTable, TableMember, TableStatus
from app.whispers import repository as whisper_repository

# 서술을 맡은 작업 하나가 쓰는 시간(초). 모두 닫기 시작한 시각(closing_at)부터 센다(app/rounds/closing.py).
# 로어북, 지난 일, 인물의 이력을 고르는 시간. 넘으면 고르지 못한 것 없이 서술한다
RETRIEVAL_BUDGET_SECONDS = 30.0
# 미리 보기를 닫고 닫기를 마무리(저장)하는 시간
SAVING_BUDGET_SECONDS = 15.0
# 작업 전체의 상한. 서술 값 잡기(BILLING_BUDGET_SECONDS) + 고르기 + 서술(다시 시도하기와 넘어가기를 합친
# NARRATION_BUDGET_SECONDS) + 마무리.
# 이 시간이 지나면 작업을 끊고 실패를 적는다. 멈춘 DB 연결이나 잠금을 하염없이 기다리지 않는다
CLOSING_JOB_SECONDS = (
    BILLING_BUDGET_SECONDS + RETRIEVAL_BUDGET_SECONDS + NARRATION_BUDGET_SECONDS + SAVING_BUDGET_SECONDS
)
# 끊긴 뒤에 실패를 적는 시간. 이것도 넘으면 적지 못한 채로 끝나고, 아래의 시간이 지난 뒤에 다시 맡길 수 있다
FAILURE_RECORD_SECONDS = 10.0
# 끊긴 작업이 정리(미리 보기 닫기)를 마칠 여유
CLOSING_RETRY_MARGIN_SECONDS = 5.0
# 닫는 중인 채로 이 시간(초)이 지나면 서술을 맡은 작업이 사라진 것으로 본다. 그때부터 다시 맡길 수 있다.
# 작업이 살아 있을 수 있는 가장 긴 시간보다 길어야 한다. 짧으면 아직 도는 서술 위에 또 서술을 맡긴다.
# 그래서 따로 적지 않고 위의 시간들을 더해서 만든다. 하나를 늘리면 이것도 늘어난다
CLOSING_RETRY_SECONDS = CLOSING_JOB_SECONDS + FAILURE_RECORD_SECONDS + CLOSING_RETRY_MARGIN_SECONDS

# 서술이 실패로 끝나도 되는 횟수. 처음 맡긴 것과 방장이 다시 맡긴 두 번이다. 여기에 닿으면 서술을 그만둔다.
# 실패한 라운드는 값을 받지 않으므로 다시 맡길 때마다 드는 원가(같은 모델로 최대 두 번)가 모두 우리 몫이다.
# 상한이 없으면 그 원가에 끝이 없다. 서술 값을 잡지 못한 실패(크레딧 모자람 등)는 모델을 부르지 않았으니 세지 않는다
NARRATION_FAILURE_LIMIT = 3

# 서술자에게 주는 쪽지(GM 에게도 보인 것)의 수. 보낸 사람마다 그 라운드의 최근 것만 이만큼(app/whispers/, #196).
# 서술 값은 앉은 사람 모두가 낸다. 한 사람이 쪽지를 쏟아 내 프롬프트를 키우면 모두가 그 값을 치른다
GM_WHISPERS_PER_SENDER = 3


class NarrationScheduler(Protocol):
    """
    서술을 뒤에서 돌게 맡기는 것의 모양. 구현은 app/rounds/closing.py 에 있다.

    이 파일이 그 파일을 불러오지 않으려고 모양만 여기 둔다. 그 파일이 이 파일을 불러온다.
    """

    def schedule(self, table_id: uuid.UUID, number: int, started: datetime) -> None:
        """
        이 테이블의 이 라운드의 서술을 맡긴다. 기다리지 않고 바로 돌아온다.

        started 는 이번에 맡기며 적은 닫기 시작한 시각(closing_at)이다. 작업이 이것으로 자기 차례인지 안다.
        """
        ...


# --- 서술을 맡은 작업이 자기 차례인지, 멈췄는지 ---


def is_run(round_: Round | None, started: datetime) -> bool:
    """
    이 라운드가 started 에 맡긴 서술을 아직 기다리고 있는가. 서술을 맡은 작업이 라운드를 읽거나 바꾸기 전에 본다.

    닫는 중이 아니면(이미 닫혔거나 없다) 아니다. 닫기 시작한 시각이 다르면 그 뒤에 다시 맡긴 것이다. 그것도 아니다.
    """
    return round_ is not None and round_.status == RoundStatus.CLOSING and round_.closing_at == started


def is_stalled(round_: Round, now: datetime) -> bool:
    """
    닫는 중인 라운드의 서술이 멈췄는가. 다시 맡겨도 되는가.

    서술이 끝내 실패한 것을 알면 바로 그렇다. 모르면 서술을 맡은 작업이 사라졌다고 볼 만큼 지났는지로 판단한다.
    now 는 지금 시각이다. 테스트가 시간을 마음대로 흘리려고 받는다.
    """
    if round_.status != RoundStatus.CLOSING:
        return False
    if round_.narration_failed_at is not None:
        return True
    return now - round_.closing_at >= timedelta(seconds=CLOSING_RETRY_SECONDS)


# --- 읽기 ---


async def get_current_round(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID) -> tuple[GameTable, Round]:
    """
    자기가 앉아 있는 테이블의 가장 최근 라운드를 돌려준다. 테이블도 함께 돌려준다.

    앉지 않았으면 TableNotFoundError, 아직 시작하지 않았으면 RoundConflictError.
    """
    table = await tables.get_table(session, user_id, table_id)
    round_ = require_started(await repository.find_latest_round(session, table_id))
    return table, round_


async def get_scene_cast(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID
) -> tuple[Round, Scene, dict[uuid.UUID, CatalogItem], Ruleset | None, dict[uuid.UUID, uuid.UUID]]:
    """
    자기가 앉아 있는 테이블의 가장 최근 라운드와, 그 장면을 돌려준다. 행동으로 겨눌 수 있는 NPC 와 몬스터들이다.

    판의 물건들(이름)도 돌려준다. 몬스터와 인물이 지닌 것의 이름이다. 지닐 수 있는 것이 없으면 비운다.
    판의 규칙에 수치(#804)가 있으면 그 규칙도 돌려준다(인물과 몬스터의 수치). 없으면 None 이다.
    둘 다 필요 없으면 판을 읽지 않는다. 로어 항목마다의 그림(#1163, 항목 → 그림)도 돌려준다. 인물의 그림이다.
    앉지 않았으면 TableNotFoundError, 아직 시작하지 않았으면 RoundConflictError.
    """
    table, round_ = await get_current_round(session, user_id, table_id)
    scene = await load_scene(session, table, round_)
    carrying = may_carry(scene)
    measured = resource_rounds.has_resources(table)
    snapshot = snapshot_of(table) if carrying or measured else None
    things = items.catalog(snapshot) if carrying else {}
    ruleset = snapshot.rulebook.rules if measured else None
    return round_, scene, things, ruleset, entry_pictures(table.content)


def may_carry(scene: Scene) -> bool:
    """장면에 무언가 지닐 수 있는 것이 있는가. 몬스터가 있거나, NPC 시트를 적은 인물이 있다."""
    return bool(scene.monsters) or any(member.definition is not None for member in scene.cast)


async def get_round(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, number: int
) -> tuple[GameTable, Round]:
    """자기가 앉아 있는 테이블의 라운드 하나를 번호로 돌려준다. 없으면 RoundNotFoundError."""
    table = await tables.get_table(session, user_id, table_id)
    round_ = await repository.find_round(session, table_id, number)
    if round_ is None:
        raise RoundNotFoundError
    return table, round_


async def get_round_charges(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, number: int
) -> list[NarrationCharge]:
    """자기가 앉아 있는 테이블의 라운드 하나의 청구들. 라운드가 없으면 RoundNotFoundError."""
    await get_round(session, user_id, table_id, number)
    return await billing_repository.find_round_charges(session, table_id, number)


async def list_rounds(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, limit: int, offset: int
) -> tuple[GameTable, list[Round], int]:
    """자기가 앉아 있는 테이블의 라운드 한 쪽과 전체 개수를 돌려준다. 처음 것부터다."""
    table = await tables.get_table(session, user_id, table_id)
    rounds = await repository.list_rounds(session, table_id, limit, offset)
    total = await repository.count_rounds(session, table_id)
    return table, rounds, total


# --- 바꾸기. 모두 테이블을 잠그고 한다 ---


def begin_closing(
    session: AsyncSession,
    table: GameTable,
    round_: Round,
    dice: Dice,
    scene: Scene,
    reason: CloseReason,
    closer_id: uuid.UUID | None = None,
) -> list[dict]:
    """
    열려 있는 라운드를 닫기 시작한다. 선언을 마감하고 행동을 판정한다. 저장하지는 않는다.
    이번 라운드에 받은 판의 업적들을 돌려준다(app/rounds/achievements.py). 계정마다의 기록은 부르는 쪽이 적는다.

    reason 은 닫는 까닭이다(모두 냄, 방장, 마감). 닫힘의 이벤트에 적는다.
    closer_id 는 라운드를 닫은 방장이다. 저절로 닫혔으면(모두 냄, 마감) 주지 않는다.
    scene 은 이번 장면의 NPC 와 몬스터들이다(load_scene).
    행동이 겨눈 NPC 와 몬스터, 몬스터가 친 캐릭터의 상태를 여기서 바꾼다.
    판정과 죽음의 굴림을 끝낸 뒤에 상태(짧은 부상)가 라운드마다의 피해를 입힌다(app/rounds/injury_ticks.py, #254).
    그 피해를 입은 사람도 이번 라운드에 다친 사람이다. 그 뒤에 상태에서 벗어나기를 굴린다(app/rounds/injury_escapes.py).
    그다음 모두 기다렸으면 시간을 건너뛴다(app/rounds/waits.py). 누가 맞았으면 깨진다.
    그다음 때가 된 부상을 끝낸다. 이번 라운드의 판정에는 아직 효과가 있었다. 늘어난 걸음으로 본다.
    오래 가는 것이 나으면 후유증 표를 굴린다(expire_injuries).
    그다음 싸우지 않은 몬스터가 사냥하거나 배회해 길 한 칸 움직인다(app/rounds/monster_roams.py, #254).
    캐릭터가 선 곳에 들어온 것만 적는다. 들어온 마리는 다음 라운드에 장면에 든다.
    그다음 길을 오거나 길게 쉰 장소에서 무작위 조우를 굴려 몬스터를 놓는다(app/rounds/wanders.py, #283).
    쉬는 중에 덮쳤으면 그 쉬기가 깨진다. 일행이 만나는 것은 다음 라운드다.
    그다음 쉰 사람이 회복하고, 고비를 넘긴 사람이 되살아나기를 굴리고, 저절로 회복한다(app/rounds/rests.py).
    그 라운드에 다친 사람의 휴식은 깨진다. 그다음 수치가 라운드마다 저절로 바뀌고, 문턱의 부상을 맞춘다
    (app/rounds/resource_rounds.py, #804). 그다음 쓰러뜨린 몬스터의 경험치를 준다(app/rounds/monster_xp.py, #286 ②).
    그다음 조건을 채운 숨긴 퀘스트를 드러내고 이룬 퀘스트를 성공으로 바꾸고
    (app/rounds/quest_goals.py), 조건이 채워진 판의 사건을 일으키고(app/rounds/happenings.py),
    기한을 넘긴 퀘스트를 실패로 바꾼다(app/rounds/deadlines.py). 이룬 것을 먼저 본다.
    기한 전 마지막 라운드에 이루었으면 성공이다. 기한의 실패로 드러날 퀘스트(잇기)가 있으면 실패 뒤에 한 번 더 본다.
    맨 끝에 조건이 채워진 판의 업적을 앉은 플레이어 모두에게 준다(app/rounds/achievements.py).
    이벤트는 행동(과 그 판정, 치료, 변화, 부상, 휴식)들 → 죽음의 굴림들 → 상태의 피해들 → 벗어나기 → 끝난 부상들 →
    나온 무리들 → 들어온 몬스터들 →
    되살아나기와 저절로 회복 → 수치의 변화와 문턱의 부상 → 몬스터의 경험치(와 오른 레벨) → 드러나고 이룬 퀘스트들 →
    일어난 사건들(과 옮긴 사람들, 준 경험치) →
    기한을 넘긴 퀘스트들 → 그 뒤에 드러나고 이룬 퀘스트들 → 받은 업적들 → 닫힘 순서로 적는다. 한 묶음이다.
    맞붙은 몬스터가 있던 라운드는 행동과 몬스터의 공격을 차례 순서로 적는다(round_.turns, app/rounds/initiative.py).
    나중에 적히는 서술과 열림도 이 묶음에 들어간다.

    주사위는 여기서만 굴린다. 열려 있는 라운드에 한 번만 부르므로 한 선언을 두 번 굴리지 않는다.
    죽음의 굴림은 행동의 판정을 끝낸 뒤에 굴린다. 이번 라운드에 회복을 받아 일어난 캐릭터는 굴리지 않는다.
    누가 굴릴지는 판정 전에 본다. 이번 라운드에 쓰러진 캐릭터는 다음 라운드부터 굴린다.
    서술자에게 줄 각자 한 일과 그때의 문체를 여기서 라운드에 굳힌다. 서술은 지금의 테이블이 아니라 이것을 읽는다.
    서술자를 부르지 않는다. 저장한 뒤에 따로 맡긴다(NarrationScheduler).

    차례대로 진행하는 테이블(#287)은 라운드 하나가 한 사람의 차례다(app/rounds/turn_order.py). 주인의 행동, 쉬기,
    기다리기, 무작위 조우, 퀘스트·사건·장·업적은 차례마다 본다. 몬스터와 싸우는 인물의 차례, 죽음의 굴림, 상태의
    피해와 벗어나기, 부상의 끝, 싸우지 않는 몬스터의 움직임, 되살아나기와 저절로 회복, 수치의 변화는 바퀴의
    마지막 차례에만 돈다(cycle_end). 그 차례의 끝에 다음 바퀴의 순서를 굴린다.
    """
    group = uuid.uuid4()
    cycle_end = turn_order.is_cycle_end(table)
    dying = find_dying(table) if cycle_end else []
    gate = turn_order.foe_gate(table, rules_of(table), cycle_end) if turn_order.is_turns(table) else None
    hurt = roll_checks(table, round_, dice, scene, gate)
    turn_order.keep_stance(table, round_)
    # 주인의 차례에 남은 차례의 사람이 모두 쓰러졌으면 이 차례로 바퀴가 끝난다(#287)
    cycle_end = cycle_end or turn_order.is_cycle_end(table)
    round_.death_saves = roll_death_saves(table, dying, dice)
    ticks = injury_ticks.settle(table, round_, dice, scene) if cycle_end else injury_ticks.Ticks()
    escapes = injury_escapes.settle(table, round_, dice, scene) if cycle_end else []
    hurt = hurt | ticks.hurt
    waits.settle(table, round_, hurt, cycle_end)
    ended = expire_injuries(table, scene, round_.cycle, dice) if cycle_end else []
    roamed = monster_roams.settle(table, scene, dice) if cycle_end else []
    roams = monster_roams.documents(table, roamed, round_.number)
    met, appeared = wanders.settle_wanders(table, round_, scene.all_monsters, dice)
    session.add_all(appeared)
    ambushed = frozenset(wanders.ambushed(table, round_, met))
    recovered = rests.settle(table, round_, hurt, dice, ambushed, cycle_end)
    drifts = resource_rounds.settle(table, round_, scene) if cycle_end else []
    defeats = monster_xp.settle(table, round_.number, scene.monsters)
    settled = quest_goals.settle_quests(table, scene.all_monsters, scene.npcs)
    occurred = happenings.settle_happenings(table, round_.number, scene.all_monsters, scene.npcs)
    happening_traps.settle(table, round_, dice, scene)
    chapter = chapters.settle(table, round_.number, scene.all_monsters, scene.npcs)
    overdue = deadlines.expire_quests(table)
    round_.expired_quests = [failure['entry_id'] for failure in overdue]
    after_overdue = quest_goals.settle_quests(table, scene.all_monsters, scene.npcs) if overdue else []
    earned = achievements.settle_achievements(table, round_.number, scene.all_monsters, scene.npcs)
    if cycle_end and turn_order.is_turns(table):
        turn_order.begin_cycle(table, rules_of(table), dice)
    moves = build_moves(table, round_, ended, recovered, [*settled, *after_overdue], met, ticks.ticks, escapes, roams)
    round_.moves = narration_request.dump_moves(moves)
    round_.narration_style = table.narration_style
    record_actions(session, table, round_, group)
    record_death_saves(session, table, round_, group)
    injury_ticks.record(session, table, ticks, round_.number, group)
    injury_escapes.record(session, table, escapes, round_.number, group)
    record_injury_endings(session, table, ended, round_.number, group)
    wanders.record_wanders(session, table, met, group)
    monster_roams.record(session, table, roams, group)
    record_recoveries(session, table, recovered, group)
    resource_rounds.record(session, table, drifts, round_.number, group)
    monster_xp.record(session, table, defeats, group)
    quest_goals.record_changes(session, table, settled, group)
    happening_traps.record(session, table, round_.number, happenings.record_happenings(session, table, occurred, group))
    chapters.record(session, table, chapter, group)
    deadlines.record_failures(session, table, overdue, group)
    quest_goals.record_changes(session, table, after_overdue, group)
    achievements.record_achievements(session, table, earned, group)
    idle = [str(user_id) for user_id in waiting_for(table, round_)]
    payload = {'number': round_.number, 'idle': idle, 'reason': reason}
    recorder.record(session, table, EventType.ROUND_CLOSED, actor_id=closer_id, payload=payload, group=group)
    round_.closing_at = datetime.now(UTC)
    return earned


async def take_snapshot(session: AsyncSession, table: GameTable, round_: Round) -> None:
    """
    지금의 게임 상태를 이 라운드의 닫기 직전으로 찍어 둔다(#288). 테이블의 앞선 사진을 덮는다. 저장하지는 않는다.

    세션이 들고 있는 바꾼 것(방금 낸 선언 같은 것)은 읽기 전에 DB 에 보내진다.
    """
    rows, values = await repository.read_state(session, table.id)
    await repository.save_snapshot(session, table.id, round_.id, snapshots.make_state(rows, values))


async def start_closing(
    session: AsyncSession,
    table: GameTable,
    round_: Round,
    dice: Dice,
    scene: Scene,
    reason: CloseReason,
    closer_id: uuid.UUID | None = None,
) -> None:
    """
    닫기 직전의 상태를 찍고(take_snapshot) 닫기 시작한다(begin_closing). 라운드를 닫는 길은 모두 이것을 쓴다.

    그 뒤에 플레이한 사람들과 받은 업적을 계정마다 적는다(app/rounds/achievements.py 의 save). 같은 트랜잭션이다.
    """
    await take_snapshot(session, table, round_)
    earned = begin_closing(session, table, round_, dice, scene, reason, closer_id)
    await achievements.save(session, table, earned)


async def lock_current_round(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID
) -> tuple[GameTable, TableMember, Round]:
    """
    자기가 앉아 있는 테이블을 잠그고, 가장 최근 라운드를 찾는다. 테이블, 자기 자리, 라운드를 돌려준다.

    앉지 않았으면 TableNotFoundError, 진행 중이 아니면 RoundConflictError.
    진행 중인 테이블의 가장 최근 라운드는 선언을 받는 중이거나 닫는 중이다.
    """
    table, member = await tables.lock_seated(session, user_id, table_id)
    require_playing(table)
    round_ = require_started(await repository.find_latest_round(session, table_id))
    return table, member, round_


async def load_scene(session: AsyncSession, table: GameTable, round_: Round) -> Scene:
    """
    이번 장면의 NPC 와 몬스터들을 읽는다. 테이블의 NPC 상태 전부와, 그중 장면의 인물들,
    그리고 살아 있는 캐릭터가 서 있는 장소들의 몬스터다.
    장면의 인물은 자리가 있으면 캐릭터가 서 있는 장소들의 인물, 없으면 라운드의 장면에 나온 인물이다(#282).

    테이블을 잠근 요청 안에서 부르면 돌려준 인물과 몬스터의 상태를 그대로 고칠 수 있다.
    조우도 무작위 조우 표(#283)도 없는 판이면 몬스터의 상태를 읽지 않는다. 테이블에 몬스터가 없다.
    """
    snapshot = snapshot_of(table)
    states = await table_repository.list_npcs(session, table.id)
    has_monsters = bool(snapshot.encounters or snapshot.wanders)
    monsters = await table_repository.list_monsters(session, table.id) if has_monsters else []
    return Scene(
        npcs=states,
        cast=cast_of(snapshot, round_.scene, states, occupied_places(table)),
        monsters=scene_monsters(snapshot, table, monsters),
        all_monsters=monsters,
    )


def hand_over(scheduler: NarrationScheduler, saved: tuple[GameTable, Round]) -> None:
    """
    방금 저장한 닫는 중인 라운드의 서술을 맡긴다. 저장한 닫기 시작한 시각을 함께 넘긴다.

    저장한 뒤에 다시 읽은 라운드(save 가 돌려준 것)를 받는다. 작업이 견주는 값이 DB 에 적힌 값과 같아야 한다.
    """
    table, round_ = saved
    scheduler.schedule(table.id, round_.number, round_.closing_at)


async def save(session: AsyncSession, table: GameTable) -> tuple[GameTable, Round]:
    """저장하고, 테이블과 가장 최근 라운드를 다시 읽어 돌려준다."""
    await tables.commit(session, table)
    return table, await repository.find_latest_round(session, table.id)


async def declare(
    session: AsyncSession,
    user_id: uuid.UUID,
    table_id: uuid.UUID,
    data: DeclarationUpdate,
    scheduler: NarrationScheduler,
    dice: Dice,
) -> tuple[GameTable, Round]:
    """
    열려 있는 라운드에 선언을 낸다. 이미 냈으면 바꾼다. 앉은 사람이 모두 냈으면 라운드를 닫기 시작한다.

    돌려주는 것은 테이블과 그 라운드다. 이 선언으로 닫기 시작했으면 "닫는 중"인 채로 돌아온다.
    서술이 끝나 다음 라운드가 열린 것은 스트림으로 알게 된다.

    닫는 중인 라운드에는 낼 수 없다(RoundConflictError). 쓰러진 사람은 행동을 붙일 수 없다(RoundConflictError).
    캐릭터가 죽은 사람은 글도 낼 수 없다(RoundConflictError).
    이 라운드에 새 캐릭터를 들인 사람도 낼 수 없다(RoundConflictError). 다음 라운드부터 낸다.
    차례대로 진행하는 테이블(#287)에서 차례의 주인이 아니면 낼 수 없다(RoundConflictError, not_your_turn).
    행동이 이 테이블의 규칙에 없는 것을 가리키면 ActionNotInRulesError.
    행동의 대상이 이 테이블에 앉은 사람이나 이번 장면의 인물이 아니면 ActionTargetError.
    겨눈 NPC 가 이미 죽었으면 RoundConflictError.
    테이블을 잠그고 한다. 마지막 두 사람이 동시에 내도 라운드는 한 번만 닫힌다.
    """
    table, member, round_ = await lock_current_round(session, user_id, table_id)
    require_open(round_)
    if sheets.is_dead(member):
        raise RoundConflictError(Conflict.CHARACTER_DEAD)
    if find_arrival(round_, user_id) is not None:
        raise RoundConflictError(Conflict.CHARACTER_ARRIVING)
    if not is_awaited(table, round_, member):
        raise RoundConflictError(Conflict.NOT_YOUR_TURN)
    scene = await load_scene(session, table, round_)
    put_declaration(round_, member, data.content, accept_action(table, member, data.action, scene))

    everyone_declared = not waiting_for(table, round_)
    if everyone_declared:
        await start_closing(session, table, round_, dice, scene, CloseReason.ALL_DECLARED)
    saved = await save(session, table)
    # 저장한 뒤에 맡기고 센다. 먼저 맡기면 서술을 맡은 작업이 아직 저장되지 않은 것을 읽는다
    if everyone_declared:
        hand_over(scheduler, saved)
        record_round_closed(CloseReason.ALL_DECLARED)
    return saved


async def force_close(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, scheduler: NarrationScheduler, dice: Dice
) -> tuple[GameTable, Round]:
    """
    방장이 라운드를 닫는다. 선언을 내지 않은 사람은 아무것도 하지 않은 것으로 넘어간다.

    방장이 아니면 NotHostError. 자리를 비운 사람 때문에 테이블이 멈추지 않게 한다.

    이미 닫는 중이면 두 가지다.
      - 맡긴 지 얼마 안 됐으면 RoundConflictError. 서술이 돌고 있다. 또 맡기면 같은 서술을 두 번 시킨다.
      - 서술이 끝내 실패했거나 한참 지났으면(is_stalled) 서술을 다시 맡긴다. 이벤트를 다시 적지는 않는다.
        주사위도 다시 굴리지 않는다. 처음 닫을 때 선언에 적어 둔 결과를 그대로 쓴다.
        닫기 시작한 시각을 지금으로 고치고 실패의 표시를 지운다. 다시 맡긴 것 위에 또 맡기지 않게 한다.
        시각이 바뀌므로 앞서 맡은 작업이 아직 살아 있어도 이 라운드를 더는 바꾸지 못한다(is_run).
        서버가 스스로 다시 맡긴 횟수(auto_retries)도 0 으로 돌린다. 방장이 지켜보며 맡긴 것이라 새로 센다.
    """
    table, _, round_ = await lock_current_round(session, host_id, table_id)
    table_state.require_host(table, host_id)

    closing = round_.status == RoundStatus.OPEN
    if closing:
        scene = await load_scene(session, table, round_)
        await start_closing(session, table, round_, dice, scene, CloseReason.HOST, closer_id=host_id)
    elif is_stalled(round_, datetime.now(UTC)):
        round_.closing_at = datetime.now(UTC)
        round_.narration_failed_at = None
        round_.auto_retries = 0
    else:
        raise RoundConflictError(Conflict.ROUND_CLOSING)

    saved = await save(session, table)
    hand_over(scheduler, saved)
    # 다시 맡긴 것은 새로 닫은 것이 아니다. 세지 않는다
    if closing:
        record_round_closed(CloseReason.HOST)
    return saved


async def revert_round(session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID) -> tuple[GameTable, Round]:
    """
    방장이 바로 앞 라운드를 되돌린다(#288). 다시 연 라운드와 테이블을 돌려준다. 규칙은 app/rounds/reverting.py 에 있다.

    방장이 아니면 NotHostError. 되돌릴 수 없으면 RoundConflictError(까닭은 reverting.blocker).
    테이블을 잠그고 한다. 한 트랜잭션이다. 덮는 도중에 실패하면 아무것도 바뀌지 않는다.
    """
    table, _, current = await lock_current_round(session, host_id, table_id)
    table_state.require_host(table, host_id)
    previous = await repository.find_round(session, table_id, current.number - 1) if current.number > 1 else None
    snapshot = await repository.find_snapshot(session, table_id)
    opened = await event_repository.find_latest(session, table_id, EventType.ROUND_OPENED)
    after = await event_repository.list_types_after(session, table_id, opened.sequence) if opened else []
    conflict = reverting.blocker(current, previous, snapshot, after)
    if conflict is not None or previous is None or snapshot is None or opened is None:
        raise RoundConflictError(conflict or Conflict.NOTHING_TO_REVERT)

    now = datetime.now(UTC)
    previous.reverted_at = now
    # 앞 라운드의 번호를 먼저 비운다(uq_table_rounds_number). 그다음 지금 라운드가 그 번호를 받는다
    await session.flush()
    deadline = opener.deadline_for(table, now)
    leaving_actor = current.actor_id
    reverting.reopen(current, previous, deadline)
    table.revert_count += 1
    await session.flush()
    await recharge_turn(session, table, current, leaving_actor, now)
    group = opened.action_group_id
    await repository.replace_state(session, table_id, snapshot.state)
    await memory_repository.delete_vectors_from(session, table_id, previous.number)
    # 덮은 표들의 객체는 낡았다. 세션에서 모두 떼고 테이블을 다시 읽는다(덮은 시계의 시각을 이벤트에 싣는다).
    # 떼지 않으면 세션이 사라진 행의 객체를 들고 있다가 저장할 때 건드릴 수 있다. 잠금은 트랜잭션에 남아 있다
    session.expunge_all()
    table = await table_repository.reload_table(session, table_id)
    payload = reverting.reverted_payload(previous.number, group, deadline, calendar.describe(table))
    recorder.record(session, table, EventType.ROUND_REVERTED, actor_id=host_id, payload=payload)
    return await save(session, table)


async def recharge_turn(
    session: AsyncSession, table: GameTable, round_: Round, leaving_actor: uuid.UUID | None, now: datetime
) -> None:
    """
    차례대로 진행하는 테이블(#287)에서 되돌려 차례의 주인이 바뀌었으면 서술 값을 걸 사람을 바꾼다.

    서술 값은 차례의 주인이 낸다. 다시 연 라운드의 홀드는 다음 차례의 주인의 것이라, 그 사람의 것은 돌려주고
    되돌아온 주인의 것을 새로 건다(이름표는 되돌린 횟수로 달라진다). 주인이 같거나 한꺼번에 진행하면 그대로다.
    """
    if leaving_actor is None or leaving_actor == round_.actor_id:
        return
    await charges.release_departed(session, table.id, leaving_actor, now)
    charges.charge_round(session, table, round_, now)


# --- 요청이 아닌 일로 닫기 시작하기. 마감이 지났거나, 안 낸 사람이 떠났다 ---


async def lock_open_round(session: AsyncSession, table_id: uuid.UUID) -> tuple[GameTable, Round] | None:
    """
    테이블을 잠그고, 선언을 받는 중인 라운드를 찾는다. 앉아 있는지는 보지 않는다(부르는 쪽이 사람이 아니다).

    테이블이 없거나, 진행 중이 아니거나, 가장 최근 라운드가 선언을 받는 중이 아니면 None.
    """
    table = await table_repository.lock_table(session, table_id)
    if table is None or table.status != TableStatus.PLAYING:
        return None
    round_ = await repository.find_latest_round(session, table_id)
    if round_ is None or round_.status != RoundStatus.OPEN:
        return None
    return table, round_


async def close_on_time(
    session: AsyncSession, table_id: uuid.UUID, now: datetime, scheduler: NarrationScheduler, dice: Dice
) -> bool:
    """
    마감이 지난 라운드를 닫기 시작한다. 닫았으면 True. 서버의 시계가 부른다(app/rounds/clock.py).

    잠근 뒤에 다시 본다. 그사이에 모두 냈거나 방장이 닫았으면, 다른 서버가 먼저 닫았으면 할 일이 없다.
    선언을 내지 않은 사람은 아무것도 하지 않은 것으로 넘어간다. 방장이 닫을 때와 같다.
    """
    found = await lock_open_round(session, table_id)
    if found is None or not is_overdue(found[1], now):
        # 잠금을 푼다. 바꾼 것이 없다. 되돌리기(rollback)는 세션이 들고 있던 객체를 낡은 것으로 만든다
        await session.commit()
        return False
    table, round_ = found
    await start_closing(session, table, round_, dice, await load_scene(session, table, round_), CloseReason.TIMEOUT)
    hand_over(scheduler, await save(session, table))
    record_round_closed(CloseReason.TIMEOUT)
    return True


async def close_when_ready(
    session: AsyncSession, table_id: uuid.UUID, scheduler: NarrationScheduler, dice: Dice
) -> bool:
    """
    기다리던 사람이 모두 냈으면 닫기 시작한다. 닫았으면 True.

    누가 떠났거나 내보내진 뒤에 부른다. 기다리던 사람이 빠지면
    남은 사람이 모두 낸 상태가 될 수 있다. 선언이 들어올 때만 보면 그 라운드는 방장이 닫을 때까지 멈춘다.
    떠나는 일과 따로 트랜잭션을 연다. 둘 사이에 서버가 죽으면 라운드는 열린 채로 남고, 방장이나 마감이 닫는다.
    """
    found = await lock_open_round(session, table_id)
    if found is None or not is_ready(*found):
        # 잠금을 푼다. 바꾼 것이 없다. 되돌리기(rollback)는 세션이 들고 있던 객체를 낡은 것으로 만든다
        await session.commit()
        return False
    table, round_ = found
    await start_closing(
        session, table, round_, dice, await load_scene(session, table, round_), CloseReason.ALL_DECLARED
    )
    hand_over(scheduler, await save(session, table))
    record_round_closed(CloseReason.ALL_DECLARED)
    return True


# --- 서술을 맡은 작업이 부르는 것. 요청 밖에서 돈다(app/rounds/closing.py) ---


async def load_closing_request(
    session: AsyncSession, table_id: uuid.UUID, number: int, started: datetime
) -> NarrationRequest | None:
    """
    닫는 중인 라운드를 서술자에게 줄 모양으로 읽는다. started 에 맡긴 서술을 기다리는 라운드가 아니면 None.

    None 이면 할 일이 없다. 다른 작업이 이미 마무리했거나, 그 뒤에 다시 맡겼거나, 테이블이 지워졌다.
    잠그지 않는다. 읽는 것은 모두 더 바뀌지 않는다.
      - 각자 한 일과 문체는 닫기 시작할 때 굳혀 둔 것이다. 그 뒤에 누가 나가도, 방장이 문체를 바꿔도 그대로다.
      - 서술 모델과 단계는 라운드를 열 때 굳혀 둔 것이다. 서술이 돌기 시작한 라운드는 방장이 바꿔도 그대로다.
        단계가 지난 기록의 라운드 수와 서술의 예산을 정한다(#387).
      - 이야기의 바탕은 판의 복사본에서 꺼낸다. 판은 고치지 않는다.
      - 지난 라운드는 닫혀서 바뀌지 않는다.
      - NPC 의 상태는 닫기 시작할 때 바뀐 뒤로 다음 라운드가 열릴 때까지 바뀌지 않는다.
      - GM 에게 보인 쪽지는 라운드가 열려 있는 동안 보낸 것이다. 닫기 시작한 뒤에 보낸 것은 다음 라운드로 간다.
      - 몬스터의 상태도 NPC 와 같다. 차례와 몬스터가 한 일은 닫기 시작할 때 라운드에 굳혀 둔 것(turns)이다.
    그래서 서술을 몇 번 다시 맡겨도 서술자는 같은 것을 받는다.
    퀘스트의 상태와 게임 안의 시각은 굳히지 않고 서술을 맡길 때의 것을 읽는다(이번 라운드에 기한을 넘긴 것만 굳힌다).
    남은 기한의 감각도 그때의 시계로 잰다. 둘 다 라운드가 닫힐 때 엔진이 바꾼 뒤로는 사람이 바꾸지 못하므로(#367)
    닫힐 때의 것과 같다.
    이야기의 바탕과 지난 라운드 몇 개는 가짜 서술자는 읽지 않고, 언어 모델의 서술자가 읽는다.
    """
    table = await table_repository.find_table(session, table_id)
    round_ = await repository.find_round(session, table_id, number)
    if table is None or not is_run(round_, started):
        return None
    steps = steps_of(round_)
    history = await repository.list_rounds_before(session, table_id, number, history_rounds(steps))
    whispers = await whisper_repository.list_for_gm(session, table_id, number, GM_WHISPERS_PER_SENDER)
    snapshot = snapshot_of(table)
    scene = await load_scene(session, table, round_)
    return NarrationRequest(
        round_number=round_.number,
        scene=round_.scene,
        moves=frozen_moves(table, round_),
        story=narration_request.to_story(snapshot),
        history=[narration_request.to_past(past) for past in history],
        style=frozen_style(table, round_),
        model=round_.narration_model,
        table_id=table.id,
        host_id=table.host_id,
        people=to_people(scene.cast, snapshot.rulebook.rules, place_names(snapshot)),
        whispers=[narration_request.to_whisper_note(whisper) for whisper in whispers],
        quests=narration_request.to_quest_notes(table, snapshot, round_.expired_quests),
        happenings=narration_request.to_happening_notes(
            table, snapshot, round_.number, labels_of(snapshot, round_.scene, scene.npcs), occupied_places(table)
        ),
        chapter=narration_request.to_chapter_note(table, snapshot, round_.number),
        monsters=to_monster_notes(snapshot, scene.monsters),
        turns=narration_request.to_turn_notes(round_.turns),
        clock=narration_request.to_clock_note(table),
        secrets=narration_request.to_secret_names(snapshot, scene.npcs, round_.scene),
        steps=steps,
        encounters=improvised.to_notes(improvised.options(table, snapshot, scene.all_monsters)),
    )


async def fail_closing(
    session: AsyncSession,
    table_id: uuid.UUID,
    number: int,
    started: datetime,
    reason: str,
    counted: bool = True,
    prices: PriceList = FREE_PRICES,
) -> None:
    """
    닫는 중인 라운드의 서술이 끝내 실패한 것을 적는다. 저장한다.

    라운드는 닫는 중에 머문다. 실패한 시각을 적어 방장이 기다리지 않고 다시 맡길 수 있게 하고,
    앉은 사람 모두에게 이벤트로 알린다. reason 은 마지막 실패의 이유다(timeout, cut_off …).

    counted 면 서술의 실패로 센다(narration_failures). 서술 값을 잡지 못해 모델을 부르지 않은 실패는 세지 않는다.
    센 횟수가 NARRATION_FAILURE_LIMIT 에 닿으면 실패로 적지 않고 서술을 그만둔다(abandon_narration).
    prices 는 그만두고 다음 라운드를 열 때 알릴 값을 찾는 가격 목록이다.

    테이블을 잠그고, 잠근 뒤에 이 라운드가 started 에 맡긴 서술을 아직 기다리는지, 실패가 적히지 않았는지 본다.
    아니면 아무것도 하지 않는다.
      - 이미 닫혔다. 마무리의 저장이 끝난 뒤에 예외가 났거나(저장 도중에 끊긴 경우를 포함한다) 다른 작업이 닫았다.
        잠금을 기다리는 동안 그 저장이 끝나므로, 잠근 뒤에 읽은 것이 실제의 상태다.
      - 그 뒤에 다시 맡겼다(닫기 시작한 시각이 다르다). 옛 작업의 실패가 지금 도는 서술에 실패를 적지 못한다.
      - 이미 실패를 적었다.

    서술이 실패로 끝나는 곳은 여기 하나다. 잡아 둔 서술 값(app/billing/)은 돌려주지 않는다.
    라운드는 닫는 중에 머물고, 방장이 다시 맡기면 같은 값으로 다시 서술한다. 테이블이 끝나면 그때 돌려준다.
    """
    table = await table_repository.lock_table(session, table_id)
    round_ = await repository.find_round(session, table_id, number)
    if table is None or not is_run(round_, started):
        return
    if round_.narration_failed_at is not None:
        return

    if counted:
        round_.narration_failures += 1
    if round_.narration_failures >= NARRATION_FAILURE_LIMIT:
        await abandon_narration(session, table, round_, reason, prices)
        return
    round_.narration_failed_at = datetime.now(UTC)
    closed = await event_repository.find_latest(session, table_id, EventType.ROUND_CLOSED)
    payload = {'round': number, 'reason': reason}
    recorder.record(session, table, EventType.NARRATION_FAILED, payload=payload, cause=closed)
    await tables.commit(session, table)


def engine_scene(table: GameTable, round_: Round) -> str:
    """
    서술 없이 엔진이 정한 결과만으로 쓴 장면. 각자 한 일과 판정의 줄을 늘어놓는다(가짜 서술자와 같은 모양).

    닫기 시작할 때 굳힌 것을 읽는다. 서술을 그만둔 라운드의 다음 장면이 된다.
    """
    turns = narration_request.to_turn_notes(round_.turns)
    lines = [f'[{round_.number} 라운드의 결과]', *round_lines(frozen_moves(table, round_), turns)]
    return '\n'.join(lines)


async def close_and_open(
    session: AsyncSession,
    table: GameTable,
    round_: Round,
    scene: str,
    paid: bool,
    cause: TableEvent | None,
    prices: PriceList = FREE_PRICES,
) -> None:
    """
    잠근 테이블의 닫는 중인 라운드를 닫고, scene 을 장면으로 하는 다음 라운드를 연다. 저장한다.

    paid 면 서술 값을 확정할 것, 아니면 돌려줄 것으로 적는다. 테이블이 끝났으면 다음 라운드를 열지 않고 돌려준다.
    cause 는 다음 라운드를 열게 한 이벤트다. 닫은 것을 먼저 DB 에 보낸다(유일 색인 uq_table_rounds_open).
    prices 로 다음 라운드의 1인 1라운드의 값을 찾아 알린다(app/rounds/round_price.py).
    """
    now = datetime.now(UTC)
    round_.closed_at = now
    playing = table.status == TableStatus.PLAYING
    if playing:
        price = await price_of(session, prices, table.narration_model, now, steps_of(table))
        await session.flush()
        opener.open_round(
            session, table, number=round_.number + 1, scene=scene, cause=cause, price=price, previous=round_
        )
    await charges.settle_round(session, round_.id, paid and playing, now)
    await tables.commit(session, table)


async def abandon_narration(
    session: AsyncSession, table: GameTable, round_: Round, reason: str, prices: PriceList = FREE_PRICES
) -> None:
    """
    잠근 테이블의 라운드의 서술을 그만둔다. 값을 받지 않고, 엔진의 결과로 다음 라운드를 연다. 저장한다.

    판정, 피해, 회복, 죽음은 닫기 시작할 때 엔진이 이미 정해 적었다. 서술이 없어도 게임의 사실은 사라지지 않는다.
    그래서 테이블을 멈추지 않는다. 앉은 사람 모두에게 이벤트로 알린다(narration_abandoned).
    """
    closed = await event_repository.find_latest(session, table.id, EventType.ROUND_CLOSED)
    payload = {'round': round_.number, 'reason': reason, 'failures': round_.narration_failures}
    abandoned = recorder.record(session, table, EventType.NARRATION_ABANDONED, payload=payload, cause=closed)
    scene = engine_scene(table, round_)
    await close_and_open(session, table, round_, scene, paid=False, cause=abandoned, prices=prices)


async def take_encounter(
    session: AsyncSession, table: GameTable, round_: Round, scene: str, closed: TableEvent | None
) -> str:
    """
    서술의 즉흥 조우(#254)의 표식을 떼고, 고른 것을 엔진이 받아들이면 몬스터를 놓는다. 표식을 뗀 장면을 돌려준다.

    고를 거리는 서술을 부탁할 때와 같은 상태로 다시 정한다(app/rounds/improvised.py). 받아들인 것은 닫힘에 잇는다.
    """
    text, number = improvised.split_tag(scene)
    if number is None:
        return text
    monsters = (await load_scene(session, table, round_)).all_monsters
    accepted = improvised.accept(table, snapshot_of(table), monsters, number, round_.number)
    if accepted is not None:
        session.add_all(accepted.made)
        improvised.record(session, table, accepted, closed)
    return text


async def finish_closing(
    session: AsyncSession,
    table_id: uuid.UUID,
    number: int,
    started: datetime,
    scene: str,
    prices: PriceList = FREE_PRICES,
) -> None:
    """
    닫는 중인 라운드를 닫고, 서술(scene)을 장면으로 하는 다음 라운드를 연다. 저장한다.

    테이블을 잠그고, 잠근 뒤에 이 라운드가 started 에 맡긴 서술을 아직 기다리는지 본다. 아니면 아무것도 하지 않는다.
    같은 라운드의 서술이 둘 돌았어도(다시 맡긴 경우) 지금 맡긴 것만 받아들여진다. 다음 라운드가 둘 열리지 않는다.
    다시 맡긴 뒤에 늦게 온 옛 서술은 버린다. 라운드를 바꾸는 것은 지금 맡긴 작업 하나뿐이다.

    서술하는 사이에 테이블이 끝났으면 라운드만 닫고 다음 라운드를 열지 않는다.

    서술 값의 청구를 같은 트랜잭션에서 정한다(app/billing/charges.py). 서술이 다음 장면이 됐으면 확정할 것,
    테이블이 끝나 버려지면 돌려줄 것이다. 결제 서버는 저장한 뒤에 부른다. 그 사이에 서버가 꺼져도 할 일이 DB 에 남는다.

    닫은 것을 먼저 DB 에 보낸다(flush). 한 테이블에 닫히지 않은 라운드는 하나뿐이라는 유일 색인이 있어서,
    앞의 것을 닫기 전에 새 것을 넣으면 DB 가 거부한다.
    """
    table = await table_repository.lock_table(session, table_id)
    round_ = await repository.find_round(session, table_id, number)
    if table is None or not is_run(round_, started):
        return

    closed = await event_repository.find_latest(session, table_id, EventType.ROUND_CLOSED)
    scene = await take_encounter(session, table, round_, scene, closed)
    await close_and_open(session, table, round_, scene, paid=True, cause=closed, prices=prices)
