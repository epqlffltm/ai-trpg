# trpg-server/app/references/service.py

"""
참고 자료를 찾고, 고른 줄을 내 로어북과 도감으로 복사한다(#482 4단계).

옮기는 규칙은 app/references/copying.py, 넣는 규칙(주인, 잠금, 상한, 건너뛰기)은 로어북과 도감의 서비스가 맡는다.
여기는 줄을 읽어 둘을 잇는다.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.bestiaries import service as bestiaries
from app.assets.bestiaries.models import Monster
from app.assets.copies import CopyOutcome
from app.assets.lorebooks import service as lorebooks
from app.assets.models import LoreEntry
from app.references import repository
from app.references.copying import check_monsters, entry_copy, monster_copy
from app.references.records import ReferenceKind, ReferenceSource, StoredReference
from app.references.srd import SRD51_ATTRIBUTION, SRD51_CHANGES, SRD51_TRANSLATED

# 자료마다의 출처 표시. 화면이 찾은 줄과 함께 보인다. 원본을 바꾼 것(빼고, 줄이고, 옮김)도 함께 적는다(CC BY 4.0)
ATTRIBUTIONS = {ReferenceSource.SRD51: f'{SRD51_ATTRIBUTION} {SRD51_CHANGES}{SRD51_TRANSLATED}'}


class ReferenceNotFoundError(Exception):
    """보낸 id 중 없는 줄이 있다. ids 는 그 id 들이다."""

    def __init__(self, ids: list[uuid.UUID]) -> None:
        super().__init__(', '.join(str(reference_id) for reference_id in ids))
        self.ids = ids


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
