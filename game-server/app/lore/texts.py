# game-server/app/lore/texts.py

"""
판에서 벡터로 바꿀 항목을 고르고, 항목을 벡터로 바꿀 글로 만든다. DB 도 모델도 모르는 순수한 함수들이다.

항목은 이름 + 키워드 + 내용을 합친 글 하나로 바꾼다(로어북 설계 때 정함).
  - 키워드만이면 문맥이 없어 부정확하다.
  - 내용만이면 제작자가 고른 이름과 키워드가 쓰이지 않는다.
항목 하나가 그대로 한 덩어리다. 항목은 500자까지라 더 쪼개지 않는다.
"""

import uuid
from collections.abc import Sequence

from app.assets.scenarios.snapshot import EntrySnapshot, Snapshot

# 한 번에 임베딩 모델에 보내는 항목의 수. 너무 많으면 한 번의 요청이 길어져 시간 제한에 걸린다
BATCH_SIZE = 32


def entry_text(entry: EntrySnapshot) -> str:
    """항목을 벡터로 바꿀 글로 만든다. 이름, 키워드, 내용이 한 줄씩이다. 키워드나 내용이 없으면 그 줄을 뺀다."""
    lines = [entry.name]
    if entry.keywords:
        lines.append(f'키워드: {", ".join(entry.keywords)}')
    if entry.content:
        lines.append(entry.content)
    return '\n'.join(lines)


def version_entries(snapshot: Snapshot) -> list[EntrySnapshot]:
    """판에 든 로어북 항목 전부. 로어북의 차례, 그 안의 항목 차례대로다."""
    return [entry for lorebook in snapshot.lorebooks for entry in lorebook.entries]


def missing_entries(entries: list[EntrySnapshot], done: set[uuid.UUID]) -> list[EntrySnapshot]:
    """아직 벡터가 없는 항목들. done 은 이미 벡터가 있는 항목의 id 다."""
    return [entry for entry in entries if entry.id not in done]


def batched[T](items: Sequence[T], size: int = BATCH_SIZE) -> list[list[T]]:
    """size 개씩 나눈다. 마지막 묶음은 더 작을 수 있다. 빈 목록이면 빈 목록이다."""
    return [list(items[start : start + size]) for start in range(0, len(items), size)]
