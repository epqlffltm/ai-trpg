# trpg-server/app/references/indexing.py

"""
이 서버의 참고 자료를 벡터로 바꿔 저장한다(색인). 규칙은 공용 코드(reference_core/indexing.py)에 있다.

여기서 이 서버의 표(app/references/models.py 의 TABLES)에 묶는다. 관리 명령(scripts/references.py index)이 부른다.
"""

from functools import partial

from reference_core import indexing as shared

from app.references.models import TABLES

index_references = partial(shared.index_references, TABLES)
