# chat-server/app/lore/texts.py

"""
판의 사본에서 벡터로 바꿀 항목을 꺼내고, 항목을 벡터로 바꿀 글로 만든다. DB 도 모델도 모르는 순수한 함수다.

항목은 이름, 키워드, 내용을 합친 글 하나로 바꾼다(trpg-server 의 app/lore/texts.py 와 같다).
  - 키워드만이면 문맥이 없어 부정확하다. 내용만이면 제작자가 고른 이름과 키워드가 쓰이지 않는다
항목 하나가 그대로 한 덩어리다. 항목은 500자까지라 더 쪼개지 않는다.
"""

import uuid
from collections.abc import Collection
from dataclasses import dataclass

from app.assets.schemas import CharacterDocument, LoreEntryDocument

# 한 번에 임베딩 모델에 보내는 항목의 수. 너무 많으면 한 번의 요청이 길어져 시간 제한에 걸린다
BATCH_SIZE = 32

# 항목을 가리키는 열쇠(로어북의 id, 항목의 id)
type EntryKey = tuple[uuid.UUID, str]


@dataclass(frozen=True)
class KeyedEntry:
    """판의 항목 하나와 그 열쇠."""

    key: EntryKey
    entry: LoreEntryDocument


def keyed_entries(document: CharacterDocument) -> list[KeyedEntry]:
    """판의 로어북들의 항목(로어북의 차례, 그 안의 차례)과 그 열쇠."""
    return [KeyedEntry((lorebook.id, entry.id), entry) for lorebook in document.lorebooks for entry in lorebook.entries]


def entry_text(entry: LoreEntryDocument) -> str:
    """항목을 벡터로 바꿀 글. 이름, 키워드, 내용이 한 줄씩이다. 키워드가 없으면 그 줄을 뺀다."""
    lines = [entry.name]
    if entry.keywords:
        lines.append(f'키워드: {", ".join(entry.keywords)}')
    lines.append(entry.content)
    return '\n'.join(lines)


def missing_entries(entries: list[KeyedEntry], done: Collection[EntryKey]) -> list[KeyedEntry]:
    """아직 벡터가 없는 항목들. 같은 열쇠가 둘이면 처음 것만이다."""
    seen = set(done)
    missing = []
    for keyed in entries:
        if keyed.key not in seen:
            seen.add(keyed.key)
            missing.append(keyed)
    return missing


def batches(entries: list[KeyedEntry]) -> list[list[KeyedEntry]]:
    """BATCH_SIZE 개씩 나눈 묶음들."""
    return [entries[start : start + BATCH_SIZE] for start in range(0, len(entries), BATCH_SIZE)]
