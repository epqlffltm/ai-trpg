# trpg-server/app/references/service.py

"""
참고 자료를 찾고, 고른 줄을 내 로어북과 도감으로 복사한다(#482 4단계).

옮기는 규칙은 app/references/copying.py, 넣는 규칙(주인, 잠금, 상한, 건너뛰기)은 로어북과 도감의 서비스가 맡는다.
여기는 줄을 읽어 둘을 잇는다.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import service as assets
from app.assets.bestiaries import repository as monsters
from app.assets.bestiaries import service as bestiaries
from app.assets.bestiaries.models import Monster
from app.assets.copies import CopiedFrom, CopyOutcome
from app.assets.lorebooks import service as lorebooks
from app.assets.models import LoreEntry, Rulebook, Scenario
from app.assets.scenarios import service as scenarios
from app.assets.scenarios.schemas import MonsterSheet
from app.assets.service import AssetNotFoundError
from app.engine.ruleset import Ruleset
from app.references import repository
from app.references.copying import check_monsters, entry_copy, monster_copy
from app.references.records import ReferenceKind, ReferenceSource, StoredReference
from app.references.sheets import Proposal, propose
from app.references.srd import SRD51_ATTRIBUTION, SRD51_CHANGES, SRD51_TRANSLATED

# 자료마다의 출처 표시. 화면이 찾은 줄과 함께 보인다. 원본을 바꾼 것(빼고, 줄이고, 옮김)도 함께 적는다(CC BY 4.0)
ATTRIBUTIONS = {ReferenceSource.SRD51: f'{SRD51_ATTRIBUTION} {SRD51_CHANGES}{SRD51_TRANSLATED}'}


class ReferenceNotFoundError(Exception):
    """보낸 id 중 없는 줄이 있다. ids 는 그 id 들이다."""

    def __init__(self, ids: list[uuid.UUID]) -> None:
        super().__init__(', '.join(str(reference_id) for reference_id in ids))
        self.ids = ids


class NoRulebookError(Exception):
    """시나리오에 룰북이 없다. 시트의 능력치와 난이도는 룰북의 것이라 제안할 수 없다."""


class NotCopiedError(Exception):
    """몬스터가 참고 자료에서 복사한 것이 아니거나, 그 참고 자료가 이제 없다. 가져올 수치가 없다."""


def attributions_of(references: Sequence[StoredReference]) -> list[str]:
    """줄들이 나온 자료의 출처 표시. 자료마다 한 번, 처음 나온 차례다."""
    sources = dict.fromkeys(reference.source for reference in references)
    return [ATTRIBUTIONS[source] for source in sources if source in ATTRIBUTIONS]


async def search_references(
    session: AsyncSession, text: str, kind: ReferenceKind | None, limit: int, offset: int
) -> tuple[list[StoredReference], int]:
    """이름으로 찾은 줄들의 한 쪽과 전체 개수. 글의 앞뒤 빈칸은 뗀다."""
    return await repository.search(session, text.strip(), kind, limit, offset)


def in_order(references: Sequence[StoredReference], ids: Sequence[uuid.UUID]) -> list[StoredReference]:
    """줄들을 보낸 id 의 차례로. 없는 id 는 건너뛴다."""
    by_id = {reference.id: reference for reference in references}
    return [by_id[reference_id] for reference_id in ids if reference_id in by_id]


async def find_references(session: AsyncSession, ids: Sequence[uuid.UUID]) -> list[StoredReference]:
    """보낸 id 의 줄들을 그 차례로. 없는 줄이 하나라도 있으면 ReferenceNotFoundError 다(하나도 넣지 않는다)."""
    found = in_order(await repository.find_many(session, ids), ids)
    missing = [reference_id for reference_id in ids if reference_id not in {reference.id for reference in found}]
    if missing:
        raise ReferenceNotFoundError(missing)
    return found


async def copy_to_lorebook(
    session: AsyncSession, owner_id: uuid.UUID, lorebook_id: uuid.UUID, ids: Sequence[uuid.UUID]
) -> CopyOutcome[LoreEntry]:
    """고른 줄들을 자기 로어북의 항목으로 복사한다. 물건은 물건, 몬스터는 종족 항목이다."""
    references = await find_references(session, ids)
    copies = [entry_copy(reference) for reference in references]
    return await lorebooks.add_copied_entries(session, owner_id, lorebook_id, copies)


async def copy_to_bestiary(
    session: AsyncSession, owner_id: uuid.UUID, bestiary_id: uuid.UUID, ids: Sequence[uuid.UUID]
) -> CopyOutcome[Monster]:
    """고른 줄들을 자기 도감의 몬스터로 복사한다. 몬스터가 아닌 줄이 있으면 NotAMonsterError 다."""
    references = await find_references(session, ids)
    check_monsters(references)
    copies = [monster_copy(reference) for reference in references]
    return await bestiaries.add_copied_monsters(session, owner_id, bestiary_id, copies)


async def scenario_ruleset(session: AsyncSession, owner_id: uuid.UUID, scenario: Scenario) -> Ruleset:
    """시나리오의 룰북의 규칙. 룰북이 없으면 NoRulebookError 다."""
    if scenario.rulebook_id is None:
        raise NoRulebookError
    rulebook = await assets.get_owned(session, Rulebook, owner_id, scenario.rulebook_id)
    return Ruleset.model_validate(rulebook.rules)


async def scenario_monster(session: AsyncSession, scenario: Scenario, monster_id: uuid.UUID) -> Monster:
    """시나리오에 붙인 도감의 몬스터 하나. 없으면 AssetNotFoundError 다(시트는 붙인 도감의 몬스터에만 적는다)."""
    for bestiary_id in scenario.bestiary_ids:
        monster = await monsters.find_monster(session, bestiary_id, monster_id)
        if monster is not None:
            return monster
    raise AssetNotFoundError


async def source_of(session: AsyncSession, monster: Monster) -> StoredReference:
    """몬스터를 복사해 온 참고 자료. 복사한 것이 아니거나 그 줄이 이제 없으면 NotCopiedError 다."""
    if monster.copied_source is None or monster.copied_key is None:
        raise NotCopiedError
    reference = await repository.find_by_key(session, monster.copied_source, monster.copied_key)
    if reference is None:
        raise NotCopiedError
    return reference


def to_monster_sheet(monster_id: uuid.UUID, proposal: Proposal) -> MonsterSheet:
    """제안을 시나리오의 몬스터 시트 모양으로. 지닌 물건은 없고 둔하지 않다(제작자가 더한다)."""
    return MonsterSheet(monster_id=monster_id, sheet=proposal.sheet, attacks=proposal.attacks)


async def propose_monster_sheet(
    session: AsyncSession, owner_id: uuid.UUID, scenario_id: uuid.UUID, monster_id: uuid.UUID
) -> tuple[MonsterSheet, list[str], CopiedFrom]:
    """
    자기 시나리오의 몬스터 하나에 시트를 제안한다. 저장하지 않는다.

    시나리오가 없거나 남의 것이면, 몬스터가 붙인 도감에 없으면 AssetNotFoundError,
    룰북이 없으면 NoRulebookError, 복사한 몬스터가 아니면 NotCopiedError,
    규칙에 SRD 의 능력치가 없으면 RulesNotSrdError.
    """
    scenario = await scenarios.get_scenario(session, owner_id, scenario_id)
    ruleset = await scenario_ruleset(session, owner_id, scenario)
    monster = await scenario_monster(session, scenario, monster_id)
    reference = await source_of(session, monster)
    proposal = propose(ruleset, reference.data)
    return (
        to_monster_sheet(monster.id, proposal),
        proposal.notes,
        CopiedFrom(source=reference.source, key=reference.key),
    )
