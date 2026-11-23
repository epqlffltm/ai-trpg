# trpg-server/app/references/repository.py

"""
참고 자료(reference_entries)와 그 벡터(reference_embeddings)를 읽고 쓰는 SQL. 커밋은 부르는 쪽이 한다.

쿼리는 공용 코드(reference_core/repository.py)에 있다. chat, story 와 함께 쓴다.
여기서 이 서버의 표(app/references/models.py 의 TABLES)에 묶어 두어, 이 서버의 코드는 표를 넘기지 않고 부른다.
"""

from functools import partial

from reference_core import repository as shared

from app.references.models import TABLES

list_stored = partial(shared.list_stored, TABLES)
list_missing = partial(shared.list_missing, TABLES)
list_aliased = partial(shared.list_aliased, TABLES)
nearest = partial(shared.nearest, TABLES)
distances_of = partial(shared.distances_of, TABLES)
find_many = partial(shared.find_many, TABLES)
find_by_key = partial(shared.find_by_key, TABLES)
search = partial(shared.search, TABLES)
