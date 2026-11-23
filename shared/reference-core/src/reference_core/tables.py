# shared/reference-core/src/reference_core/tables.py

"""
서버의 참고 자료 표 둘을 묶어 넘기는 꾸러미.

표는 서버마다 제 Base 와 DB 로 만든다(서버의 app/references/models.py).
칸과 제약은 reference_core/columns.py 에서 물려받는다.
  - entry: reference_entries. id, source, key, kind, name, aliases(글의 배열), content, data(JSONB), name_ko, content_ko
  - embedding: reference_embeddings. id, reference_id(entry 의 id, 지우면 함께 지워진다), model, embedding(pgvector)
같은 자료에 같은 key 는 하나다(source, key 의 유일 제약). 같은 모델과 같은 줄의 벡터도 하나다(model, reference_id).

ORM 클래스는 서버의 Base(메타데이터)에 붙어야 해서 서버가 만들고, 공용 코드는 그 클래스를 받는다.
마이그레이션은 서버마다 만든다. 서버의 alembic check 가 표와 마이그레이션이 맞는지 본다.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReferenceTables:
    """서버의 표 둘(ORM 클래스). 서버가 app/references/models.py 에 하나 만들어 둔다."""

    entry: type[Any]
    embedding: type[Any]
