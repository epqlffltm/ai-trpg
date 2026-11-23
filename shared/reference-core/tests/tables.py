# shared/reference-core/tests/tables.py

"""
테스트의 참고 자료 표 둘. 서버의 표(app/references/models.py)처럼 칸과 제약을 reference_core/columns.py 에서 물려받는다.

공용 코드는 표를 꾸러미(ReferenceTables)로 받는다. 서버의 표 대신 이것을 넘겨 쿼리를 본다.
"""

from sqlalchemy.orm import DeclarativeBase

from reference_core.columns import ReferenceEmbeddingColumns, ReferenceEntryColumns
from reference_core.tables import ReferenceTables


class Base(DeclarativeBase):
    """테스트의 표만 담는 바탕."""


class Entry(ReferenceEntryColumns, Base):
    """테스트의 reference_entries."""


class Embedding(ReferenceEmbeddingColumns, Base):
    """테스트의 reference_embeddings."""


TABLES = ReferenceTables(entry=Entry, embedding=Embedding)
