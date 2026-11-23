# trpg-server/app/references/models.py

"""
참고 자료의 테이블 둘.

  - reference_entries: 자료의 한 줄. 자료(source)와 key 로 찾는다. 다시 넣어도 id 는 그대로다.
  - reference_embeddings: 한 줄을 한 임베딩 모델로 바꾼 벡터. 줄 하나, 모델 하나마다 한 줄이다.

칸과 제약은 공용 코드(reference_core/columns.py)에 있다. chat, story 의 같은 표와 모양이 같다.

로어북의 벡터(lore_embeddings)와 따로 둔다. 로어북의 벡터는 게시한 판마다 만들고 판이 굳어 있어 다시 만들 일이 없다.
참고 자료는 판과 상관없이 하나뿐이고, 운영자가 자료를 다시 넣으면 바뀐 줄의 벡터만 다시 만든다.
로어북 항목과 같은 테이블에 넣으면 주인과 판이 없는 줄이 섞이고, 로어북과 도감이 asset 서버로 옮겨 갈 때 함께 딸려 간다.
"""

from reference_core.columns import ReferenceEmbeddingColumns, ReferenceEntryColumns
from reference_core.tables import ReferenceTables

from app.core.database import Base


class ReferenceEntry(ReferenceEntryColumns, Base):
    """참고 자료의 한 줄. 서술자가 읽는 글(content)과 원본의 수치(data)를 함께 둔다."""


class ReferenceEmbedding(ReferenceEmbeddingColumns, Base):
    """참고 자료의 한 줄을 한 모델로 바꾼 벡터. 줄의 글이 바뀌면 지우고 다시 만든다(reference_core/loading.py)."""


# 공용 코드(reference_core 의 repository, loading, indexing, search)에 넘기는 이 서버의 표 둘
TABLES = ReferenceTables(entry=ReferenceEntry, embedding=ReferenceEmbedding)
