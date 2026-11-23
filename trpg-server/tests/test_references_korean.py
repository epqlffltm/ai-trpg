# trpg-server/tests/test_references_korean.py

"""
게임 서버에서 참고 자료의 한국어 이름과 글을 쓰는 곳을 검증한다. 번역 파일과 붙이기의 규칙은 공용 코드의 시험이 본다
(shared/reference-core/tests/test_translations.py).

보는 것.
  - 서술자에게 가는 이름과 글이 한국어다(없으면 원본).
  - DB 에 쓰고 읽으면 한국어 이름과 글이 같다.
"""

import uuid

import pytest
from reference_core.records import (
    ReferenceDocument,
    ReferenceKind,
    ReferenceOrigin,
    ReferenceRecord,
    ReferenceSource,
    StoredReference,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.references import repository
from app.references.loading import load_document
from app.references.retrieval import to_reference_note


def record(key: str = 'equipment/torch', **values) -> ReferenceRecord:
    defaults = {'kind': ReferenceKind.ITEM, 'name': 'Torch', 'content': 'A torch burns.'}
    return ReferenceRecord(key=key, **{**defaults, **values})


def stored(**values) -> StoredReference:
    defaults = {'id': uuid.uuid4(), 'key': 'equipment/torch', 'name': 'Torch', 'content': 'A torch burns.'}
    return StoredReference(**{**defaults, **values})


def document(records: list[ReferenceRecord]) -> ReferenceDocument:
    origin = ReferenceOrigin(dataset='test', revision='abc', license='CC-BY-4.0', attribution='SRD 5.1')
    return ReferenceDocument(format=1, source=ReferenceSource.SRD51, origin=origin, entries=records)


def test_the_narrator_gets_the_korean_name_and_text():
    reference = stored(name_ko='횃불', content_ko='횃불이 탄다.')
    english = stored()

    note = to_reference_note(reference)
    assert (note.name, note.content) == ('횃불', '횃불이 탄다.')
    assert (to_reference_note(english).name, to_reference_note(english).content) == ('Torch', 'A torch burns.')


@pytest.mark.usefixtures('clean_tables')
async def test_the_korean_name_and_text_are_stored(session: AsyncSession):
    await load_document(session, document([record(name_ko='횃불', content_ko='횃불이 탄다.', aliases=['횃불'])]))

    (torch,) = await repository.list_stored(session, ReferenceSource.SRD51)

    assert (torch.name_ko, torch.content_ko, torch.shown_name) == ('횃불', '횃불이 탄다.', '횃불')
