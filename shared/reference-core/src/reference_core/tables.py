# shared/reference-core/src/reference_core/tables.py

"""
서버의 참고 자료 표 둘을 묶어 넘기는 꾸러미.

표는 서버마다 제 Base 와 스키마로 만든다(서버의 app/references/models.py). 공용 코드가 쓰는 칸의 이름은 서버가 같다.
  - entry: reference_entries. id, source, key, kind, name, aliases(글의 배열), content, data(JSONB), name_ko, content_ko
  - embedding: reference_embeddings. id, reference_id(entry 의 id, 지우면 함께 지워진다), model, embedding(pgvector)
같은 자료에 같은 key 는 하나다(source, key 의 유일 제약). 같은 모델과 같은 줄의 벡터도 하나다(model, reference_id).

공용 코드가 칸까지 정의하지 않고 서버의 표를 받는다. 모델 목록의 표(catalog_core/tables.py)와 같은 까닭이다.
표의 제약(받는 자료와 종류)과 마이그레이션은 서버의 것이고, 칸의 이름이 어긋나면 서버의 테스트(실제 DB)가 잡는다.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReferenceTables:
    """서버의 표 둘(ORM 클래스). 서버가 app/references/models.py 에 하나 만들어 둔다."""

    entry: type[Any]
    embedding: type[Any]
