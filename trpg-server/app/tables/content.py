# trpg-server/app/tables/content.py

"""
테이블의 판의 복사본(game_tables.content)을 읽는다(#1264). 같은 복사본은 테이블 하나에서 한 번만 검증한다.

  - read_snapshot 은 부를 때마다 문서 전체를 pydantic 으로 검증한다. 라운드 하나를 닫는 동안 수십 번 불린다.
  - snapshot_of 는 읽은 판을 테이블 객체에 그 문서와 함께 붙여 둔다. 다음에 같은 문서 객체면 붙여 둔 판을 준다.
  - 문서가 바뀌면 저절로 다시 읽는다. 복사본을 고치는 곳은 문서를 통째로 바꿔 넣는다(새 dict).
    테이블을 만들 때(app/tables/building.py)와 캠페인의 앞 편의 퀘스트를 넘길 때(app/campaigns/service.py 의
    hand_down_quests)다. DB 에서 다시 읽어도 새 dict 가 온다. 붙여 둔 것이 그 문서 객체를 쥐고 있어
    같은 id 의 다른 dict 로 헷갈리는 일이 없다.
  - 문서를 제자리에서 고치면(table.content[...] = ...) 알아채지 못한다. JSONB 칸이라 제자리의 변경은 저장도
    되지 않으므로 그렇게 고치는 곳은 없어야 한다(tests/test_table_content.py 가 본다).
  - 돌려주는 판은 여러 곳이 함께 쓴다. 고치지 않는다(판은 읽기만 하는 값이다).

DB 를 모른다. 테이블 객체의 칸 하나(붙여 둔 것)만 쓴다.
"""

from typing import Any

from app.assets.scenarios.snapshot import Snapshot, read_snapshot

# 테이블 객체에 붙여 두는 칸의 이름. (읽은 문서, 그 판)이다. 매핑한 칸이 아니라 DB 에 가지 않는다
CACHE_ATTRIBUTE = '_content_snapshot'


def cached_snapshot(table: Any) -> Snapshot | None:
    """붙여 둔 판. 붙여 둔 것이 지금의 문서 객체에서 읽은 것일 때만 준다. 아니면 None."""
    cached = getattr(table, CACHE_ATTRIBUTE, None)
    if cached is None or cached[0] is not table.content:
        return None
    return cached[1]


def snapshot_of(table: Any) -> Snapshot:
    """테이블의 판의 복사본을 읽는다. 같은 문서 객체를 이미 읽었으면 그 판을 준다."""
    found = cached_snapshot(table)
    if found is not None:
        return found
    content = table.content
    snapshot = read_snapshot(content)
    setattr(table, CACHE_ATTRIBUTE, (content, snapshot))
    return snapshot
