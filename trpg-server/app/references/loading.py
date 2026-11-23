# trpg-server/app/references/loading.py

"""
데이터 파일을 이 서버의 표에 맞춘다(넣기). 규칙은 공용 코드(reference_core/loading.py)에 있다.

여기서 이 서버의 표(app/references/models.py 의 TABLES)에 묶는다.
관리 명령(scripts/references.py load)과 테스트가 부른다.
"""

from functools import partial

from reference_core import loading as shared

from app.references.models import TABLES

load_document = partial(shared.load_document, TABLES)
