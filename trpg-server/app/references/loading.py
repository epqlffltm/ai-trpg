# trpg-server/app/references/loading.py

"""
데이터 파일의 줄들을 DB 에 맞춘다(넣기). 자료 하나를 통째로 맞춘다.

  - 파일에만 있는 줄은 더한다.
  - 둘 다 있는 줄은 파일의 값으로 고친다. id 는 그대로다.
    벡터로 바꿀 글(이름, 다른 이름, 글)이 바뀐 줄은 벡터를 지운다. 다음 색인이 새로 만든다.
    수치(data)나 종류만 바뀐 줄은 벡터를 그대로 둔다. 벡터는 글에서 만든 것이다.
  - DB 에만 있는 줄은 지운다(벡터도 함께 지워진다). 원본에서 빠진 것이다.
같은 파일을 두 번 넣으면 두 번째는 아무것도 바꾸지 않는다. 한 트랜잭션이라 도중에 실패하면 아무것도 바뀌지 않는다.

무엇을 바꿀지 정하는 것(plan_sync)은 순수한 함수다. DB 에 쓰는 것(apply_sync)과 나눈다.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.references import repository
from app.references.records import ReferenceDocument, ReferenceRecord, StoredReference
from app.references.texts import reference_text


@dataclass(frozen=True)
class SyncPlan:
    """자료 하나를 맞추려고 할 일. added 와 updated 는 파일의 줄, removed 는 DB 의 줄이다."""

    added: list[ReferenceRecord]
    updated: list[ReferenceRecord]
    # updated 중 벡터를 다시 만들어야 하는 줄의 key
    reworded: set[str]
    removed: list[StoredReference]

    @property
    def changed(self) -> bool:
        """바꿀 것이 있는가."""
        return bool(self.added or self.updated or self.removed)


def same_text(stored: StoredReference, record: ReferenceRecord) -> bool:
    """벡터로 바꿀 글이 같은가."""
    incoming = StoredReference(
        id=stored.id,
        key=record.key,
        name=record.name,
        aliases=record.aliases,
        content=record.content,
        content_ko=record.content_ko,
    )
    return reference_text(stored) == reference_text(incoming)


def plan_sync(stored: Sequence[StoredReference], records: Sequence[ReferenceRecord]) -> SyncPlan:
    """DB 의 줄들(stored)을 파일의 줄들(records)에 맞출 일을 정한다. 값이 모두 같은 줄은 고치지 않는다."""
    by_key = {reference.key: reference for reference in stored}
    keys = {record.key for record in records}
    added = [record for record in records if record.key not in by_key]
    updated = [record for record in records if record.key in by_key and not by_key[record.key].matches(record)]
    reworded = {record.key for record in updated if not same_text(by_key[record.key], record)}
    removed = [reference for reference in stored if reference.key not in keys]
    return SyncPlan(added=added, updated=updated, reworded=reworded, removed=removed)


async def apply_sync(session: AsyncSession, document: ReferenceDocument, plan: SyncPlan) -> None:
    """정한 일을 DB 에 쓴다. 커밋은 부르는 쪽이 한다."""
    source = document.source
    await repository.delete_entries(session, [reference.id for reference in plan.removed])
    await repository.add_entries(session, source, plan.added)
    await repository.update_entries(session, source, plan.updated)
    await repository.delete_embeddings(session, source, plan.reworded)


async def load_document(session: AsyncSession, document: ReferenceDocument) -> SyncPlan:
    """데이터 파일 하나를 DB 에 맞추고 한 일을 돌려준다. 커밋까지 한다."""
    stored = await repository.list_stored(session, document.source)
    plan = plan_sync(stored, document.entries)
    if plan.changed:
        await apply_sync(session, document, plan)
        await session.commit()
    return plan
