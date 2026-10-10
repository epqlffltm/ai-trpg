# game-server/tests/indexers.py

"""
판의 색인을 맡기지 않는 것. 게시 함수(publishing.publish)를 직접 부르는 테스트가 판만 필요할 때 꽂는다.

로어북 검색을 보는 테스트는 이것을 쓰지 않는다(tests/test_lore_indexing.py 는 API 로 게시한다).
"""

import uuid


class NoIndexer:
    """publishing.VersionIndexer 의 모양을 따르지만 아무것도 맡기지 않는다."""

    def schedule(self, version_id: uuid.UUID) -> None:
        return None


NO_INDEXER = NoIndexer()
