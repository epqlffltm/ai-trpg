# chat-server/app/references/models.py

"""
참고 자료의 표 둘(#1338). 게임 서버, story 와 같은 데이터 파일을 이 서버의 DB 에 넣는다(2026-11-22 유저 결정의 안 A).

  - reference_entries: 자료의 한 줄. 자료(source)와 key 로 찾는다. 다시 넣어도 id 는 그대로다.
  - reference_embeddings: 한 줄을 한 임베딩 모델로 바꾼 벡터. 줄 하나, 모델 하나마다 한 줄이다.

칸과 제약은 공용 코드(reference_core/columns.py)에 있다. 줄은 관리 명령(scripts/references.py)만 넣는다.
로어북의 벡터(lore_embeddings)와 따로 둔다. 로어북의 벡터는 판의 사본마다 있고 주인이 있다(탈퇴하면 지운다).
참고 자료는 주인이 없고 하나뿐이다. 운영자가 자료를 다시 넣으면 바뀐 줄의 벡터만 다시 만든다.
"""

from reference_core.columns import ReferenceEmbeddingColumns, ReferenceEntryColumns
from reference_core.tables import ReferenceTables

from app.core.database import Base


class ReferenceEntry(ReferenceEntryColumns, Base):
    """참고 자료의 한 줄. 모델이 읽는 글(content)과 원본의 수치(data)를 함께 둔다."""


class ReferenceEmbedding(ReferenceEmbeddingColumns, Base):
    """참고 자료의 한 줄을 한 모델로 바꾼 벡터. 줄의 글이 바뀌면 지우고 다시 만든다(reference_core/loading.py)."""


# 공용 코드(reference_core 의 loading, indexing, finder)에 넘기는 이 서버의 표 둘
TABLES = ReferenceTables(entry=ReferenceEntry, embedding=ReferenceEmbedding)
