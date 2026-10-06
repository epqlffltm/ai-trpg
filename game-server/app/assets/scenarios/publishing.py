# game-server/app/assets/scenarios/publishing.py

"""
시나리오를 게시한다. 초안의 지금 내용을 판으로 굳힌다.

게시는 "굳히기"다. 남에게 보이게 하는 것(공개)은 따로다. 판은 만든 사람만 본다.
SQL 을 모른다. 판을 읽고 쓰는 일은 repository.py 에 맡긴다.
판을 고치거나 지우는 함수는 없다. 고칠 것이 있으면 초안을 고치고 새 판을 낸다.
"""

import enum
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import service as assets
from app.assets.lorebooks import repository as entries
from app.assets.models import (
    PLAYER_MADE_MODES,
    CharacterMode,
    Lorebook,
    LoreEntry,
    Rulebook,
    Scenario,
    ScenarioVersion,
    World,
)
from app.assets.scenarios import repository
from app.assets.scenarios.schemas import VersionCreate
from app.assets.scenarios.snapshot import build_snapshot
from app.assets.service import AssetNotFoundError
from app.engine.ruleset import Ruleset
from app.engine.sheet import Sheet, fits


class Problem(enum.StrEnum):
    """게시할 수 없는 이유."""

    # 룰북이 없다. 진행 방식이 없으면 테이블이 성립하지 않는다
    RULEBOOK_MISSING = 'rulebook_missing'
    # 스타팅이 하나도 없다. 첫 장면은 제작자가 정한다
    OPENING_MISSING = 'opening_missing'
    # 시트가 없는 프리젠이 있다. 판 안의 프리젠은 모두 숫자를 갖는다
    PREGEN_SHEET_MISSING = 'pregen_sheet_missing'
    # 룰북의 규칙에 맞지 않는 시트를 가진 프리젠이 있다. 능력치가 빠졌거나 남거나, 점수가 범위 밖이다
    PREGEN_SHEET_INVALID = 'pregen_sheet_invalid'
    # 캐릭터를 직접 만들 수 있게 했는데 기본 시트가 없다. 그 사람이 받을 숫자가 없다
    DEFAULT_SHEET_MISSING = 'default_sheet_missing'
    # 기본 시트가 룰북의 규칙에 맞지 않는다
    DEFAULT_SHEET_INVALID = 'default_sheet_invalid'
    # 프리젠만 허용했는데 프리젠이 추천 인원의 최소보다 적다. 그 인원이 앉을 수 없다
    PREGENS_TOO_FEW = 'pregens_too_few'
    # 플레이어가 능력치를 정하는 방식을 허용했는데 최대 HP 를 구하는 값(기준값과 상한)이 없다
    PLAYER_MADE_HP_MISSING = 'player_made_hp_missing'
    # 점수제를 허용했는데 룰북의 규칙에 점수제가 없다. 총점도 값표도 없어서 아무도 캐릭터를 만들 수 없다
    POINT_BUY_MISSING = 'point_buy_missing'


class ScenarioNotReadyError(Exception):
    """
    시나리오가 게시할 조건을 갖추지 못했다.

    problems 는 갖추지 못한 조건 전부다. 하나씩 고치고 다시 시도하지 않게 한 번에 알려 준다.
    """

    def __init__(self, problems: list[Problem]) -> None:
        super().__init__()
        self.problems = problems


@dataclass
class Parts:
    """시나리오가 가리키는 자산들. 게시할 때 한 번 읽어서, 조건을 검사하고 판에 굳히는 데 함께 쓴다."""

    rulebook: Rulebook | None
    world: World | None
    # 로어북과 그 항목들
    lorebooks: list[tuple[Lorebook, list[LoreEntry]]]


async def load_parts(session: AsyncSession, owner_id: uuid.UUID, scenario: Scenario) -> Parts:
    """시나리오가 가리키는 자산들을 읽는다."""
    rulebook = None
    if scenario.rulebook_id is not None:
        rulebook = await assets.get_owned(session, Rulebook, owner_id, scenario.rulebook_id)

    world = None
    if scenario.world_id is not None:
        world = await assets.get_owned(session, World, owner_id, scenario.world_id)

    lorebooks = []
    for lorebook_id in scenario.lorebook_ids:
        lorebook = await assets.get_owned(session, Lorebook, owner_id, lorebook_id)
        lorebooks.append((lorebook, await entries.list_entries(session, lorebook_id)))

    return Parts(rulebook=rulebook, world=world, lorebooks=lorebooks)


def read_ruleset(rulebook: Rulebook | None) -> Ruleset | None:
    """룰북의 규칙을 읽는다. 룰북이 없으면 None 이다."""
    if rulebook is None:
        return None
    return Ruleset.model_validate(rulebook.rules)


def read_pregen_sheets(scenario: Scenario) -> list[Sheet | None]:
    """프리젠들의 시트를 읽는다. 시트가 없는 프리젠의 자리는 None 이다."""
    documents = [pregen.get('sheet') for pregen in scenario.pregens]
    return [Sheet.model_validate(document) if document else None for document in documents]


def find_pregen_problems(scenario: Scenario, ruleset: Ruleset | None) -> list[Problem]:
    """
    프리젠의 시트에서 문제를 찾는다. 프리젠이 여럿 틀려도 같은 문제는 한 번만 적는다.

    룰북이 없으면 규칙에 맞는지는 볼 수 없다. 그때는 시트가 있는지만 본다.
    프리젠을 허용하지 않아도 본다. 판 안의 프리젠은 어느 것이든 시트가 있어야 판을 읽는 쪽이 단순하다.
    """
    sheets = read_pregen_sheets(scenario)
    problems = []
    if any(sheet is None for sheet in sheets):
        problems.append(Problem.PREGEN_SHEET_MISSING)
    if ruleset and any(sheet and not fits(ruleset, sheet) for sheet in sheets):
        problems.append(Problem.PREGEN_SHEET_INVALID)
    return problems


def find_default_sheet_problems(scenario: Scenario, ruleset: Ruleset | None) -> list[Problem]:
    """
    기본 시트에서 문제를 찾는다.

    직접 만들기를 허용했으면 기본 시트가 있어야 한다. 허용하지 않았으면 없어도 된다.
    있으면 허용했든 안 했든 규칙에 맞아야 한다. 판에 들어가기 때문이다.
    """
    if scenario.default_sheet is None:
        needed = CharacterMode.CUSTOM in scenario.character_modes
        return [Problem.DEFAULT_SHEET_MISSING] if needed else []
    if ruleset and not fits(ruleset, Sheet.model_validate(scenario.default_sheet)):
        return [Problem.DEFAULT_SHEET_INVALID]
    return []


def find_player_made_problems(scenario: Scenario) -> list[Problem]:
    """
    플레이어가 능력치를 정하는 방식에서 문제를 찾는다.

    그런 방식을 하나라도 허용했으면 최대 HP 를 구하는 값이 있어야 한다. 플레이어는 최대 HP 를 직접 적지 못한다.
    허용하지 않았으면 없어도 된다.
    """
    allows_player_made = any(mode in PLAYER_MADE_MODES for mode in scenario.character_modes)
    if allows_player_made and scenario.player_made_hp is None:
        return [Problem.PLAYER_MADE_HP_MISSING]
    return []


def find_point_buy_problems(scenario: Scenario, ruleset: Ruleset | None) -> list[Problem]:
    """
    점수제에서 문제를 찾는다.

    점수제를 허용했으면 룰북의 규칙에 점수제(총점과 값표)가 있어야 한다. 허용하지 않았으면 없어도 된다.
    룰북이 없으면 볼 수 없다. 그때는 룰북이 없다는 문제가 따로 적힌다.
    """
    allowed = CharacterMode.POINT_BUY in scenario.character_modes
    if allowed and ruleset is not None and ruleset.point_buy is None:
        return [Problem.POINT_BUY_MISSING]
    return []


def find_seating_problems(scenario: Scenario) -> list[Problem]:
    """
    허용한 방식으로 사람이 앉을 수 있는지 본다.

    프리젠 하나는 한 사람만 고른다. 프리젠만 허용했으면 프리젠의 수가 곧 앉을 수 있는 사람의 수다.
    추천 인원의 최소만큼은 앉을 수 있어야 한다.
    """
    pregen_only = list(scenario.character_modes) == [CharacterMode.PREGEN]
    if pregen_only and len(scenario.pregens) < scenario.min_players:
        return [Problem.PREGENS_TOO_FEW]
    return []


def find_problems(scenario: Scenario, parts: Parts) -> list[Problem]:
    """게시할 수 없는 이유를 전부 찾는다. 없으면 빈 목록이다."""
    ruleset = read_ruleset(parts.rulebook)
    problems = []
    if parts.rulebook is None:
        problems.append(Problem.RULEBOOK_MISSING)
    if not scenario.openings:
        problems.append(Problem.OPENING_MISSING)
    problems.extend(find_pregen_problems(scenario, ruleset))
    problems.extend(find_default_sheet_problems(scenario, ruleset))
    problems.extend(find_player_made_problems(scenario))
    problems.extend(find_point_buy_problems(scenario, ruleset))
    problems.extend(find_seating_problems(scenario))
    return problems


def build_version(scenario: Scenario, rulebook: Rulebook, parts: Parts, number: int, note: str) -> ScenarioVersion:
    """시나리오와 자산들에서 판 객체를 만든다. 아직 저장하지 않는다."""
    snapshot = build_snapshot(scenario, rulebook, parts.world, parts.lorebooks)
    return ScenarioVersion(
        scenario_id=scenario.asset_id,
        number=number,
        note=note,
        # mode='json': UUID 같은 값을 JSON 에 넣을 수 있는 글자로 바꾼다
        snapshot=snapshot.model_dump(mode='json'),
    )


async def publish(
    session: AsyncSession, owner_id: uuid.UUID, scenario_id: uuid.UUID, data: VersionCreate
) -> ScenarioVersion:
    """
    자기 시나리오를 게시한다. 시나리오가 없으면 AssetNotFoundError, 조건을 갖추지 못했으면 ScenarioNotReadyError.

    시나리오를 잠그고 한다. 번호는 "지금까지의 가장 큰 번호 + 1"이라, 두 요청이 동시에 세면 같은 번호를 얻는다.
    잠그면 나중 요청은 앞의 판이 저장된 뒤에 센다. DB 의 UNIQUE 는 잠금을 빠뜨렸을 때의 마지막 방어선이다.
    """
    scenario = await assets.lock_owned(session, Scenario, owner_id, scenario_id)
    parts = await load_parts(session, owner_id, scenario)

    problems = find_problems(scenario, parts)
    if problems or parts.rulebook is None:
        raise ScenarioNotReadyError(problems)

    # 다음 번호는 지금까지의 가장 큰 번호에 1 을 더한 것이다
    number = await repository.last_number(session, scenario_id) + 1
    version = build_version(scenario, parts.rulebook, parts, number, data.note)
    repository.add_version(session, version)
    await session.commit()
    return version


async def list_versions(session: AsyncSession, owner_id: uuid.UUID, scenario_id: uuid.UUID) -> list[ScenarioVersion]:
    """자기 시나리오의 판을 최근 것부터 전부 돌려준다. 시나리오가 없으면 AssetNotFoundError."""
    await assets.get_owned(session, Scenario, owner_id, scenario_id)
    return await repository.list_versions(session, scenario_id)


async def get_version(
    session: AsyncSession, owner_id: uuid.UUID, scenario_id: uuid.UUID, number: int
) -> ScenarioVersion:
    """자기 시나리오의 판 하나를 돌려준다. 시나리오나 판이 없으면 AssetNotFoundError."""
    await assets.get_owned(session, Scenario, owner_id, scenario_id)
    version = await repository.find_version(session, scenario_id, number)
    if version is None:
        raise AssetNotFoundError
    return version
