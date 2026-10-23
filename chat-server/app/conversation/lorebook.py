# chat-server/app/conversation/lorebook.py

"""
로어북의 항목을 골라 카드에 넣는다(#672, docs/architecture/chat-server.md 의 "로어북"). DB 도 모델도 모른다.

항목은 캐릭터의 판에 복사된 로어북들에 있다(asset 의 판 형식 8). 이 파일은 항목의 모양(LoreEntry)만 안다.
고르는 법은 업계의 로어북(World Info)과 같다.
  - 상시(constant) 항목은 늘 넣는다
  - 나머지는 최근 말(SCAN_MESSAGES 개, 이번에 보낸 말 포함)에 키워드 가운데 하나가 나오면 넣는다.
    대소문자는 가리지 않고, 글자가 이어져 있으면 맞는다(한국어는 조사가 붙으므로 낱말의 경계를 보지 않는다)
  - 차례: 상시가 먼저(판의 차례), 그다음 키워드가 가장 최근에 나온 것부터(같으면 판의 차례)
  - 상한: 항목 MAX_ENTRIES 개, 글자 MAX_CHARS 까지. 들어가지 않는 항목은 건너뛰고 다음 것을 본다
같은 항목이 두 로어북에 있어도(id 가 같아도) 따로 센다. 로어북마다 따로 만든 것이다.
뜻으로 찾는 검색(임베딩)은 다음에 더한다. 그때도 키워드는 함께 쓴다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

# 키워드를 찾는 최근 말의 수(이번에 보낸 말을 넣어서)
SCAN_MESSAGES = 4
# 카드에 넣는 항목의 수와 글자(이름과 내용)의 상한. 늘 가는 기억 메모(20 × 300자)보다 작게 둔다
MAX_ENTRIES = 8
MAX_CHARS = 2000


class LoreEntry(Protocol):
    """항목 하나의 모양. 판의 항목(chat 의 app/assets/schemas.py 의 LoreEntry)이 이 모양이다."""

    name: str
    content: str
    keywords: list[str]
    constant: bool


@dataclass(frozen=True)
class Candidate:
    """고를 거리 하나. recency 는 키워드가 나온 가장 뒤의 자리다(상시면 쓰지 않는다)."""

    entry: LoreEntry
    recency: int


def scanned_text(recent: Sequence[str]) -> str:
    """키워드를 찾을 글. 최근 말 SCAN_MESSAGES 개를 이어 붙이고 대소문자를 접는다. 뒤의 말일수록 뒤에 있다."""
    return '\n'.join(recent[-SCAN_MESSAGES:]).casefold()


def last_mention(entry: LoreEntry, text: str) -> int:
    """항목의 키워드가 글에 나온 가장 뒤의 자리. 하나도 없으면 -1."""
    found = [text.rfind(keyword.casefold()) for keyword in entry.keywords if keyword.strip()]
    return max(found, default=-1)


def candidates(entries: Sequence[LoreEntry], text: str) -> list[Candidate]:
    """
    넣을 거리들. 상시가 먼저, 그다음 키워드가 가장 최근에 나온 것부터다.
    정렬은 안정적이라 같은 자리면 판의 차례가 남는다.
    """
    constant = [Candidate(entry, 0) for entry in entries if entry.constant]
    triggered = [
        Candidate(entry, last_mention(entry, text))
        for entry in entries
        if not entry.constant and last_mention(entry, text) >= 0
    ]
    triggered.sort(key=lambda candidate: -candidate.recency)
    return constant + triggered


def entry_size(entry: LoreEntry) -> int:
    """항목이 차지하는 글자(이름과 내용)."""
    return len(entry.name) + len(entry.content)


def within_limits(chosen: Sequence[Candidate]) -> list[LoreEntry]:
    """차례대로 상한(수와 글자) 안에 드는 것만 고른다. 들어가지 않는 것은 건너뛴다."""
    picked: list[LoreEntry] = []
    used = 0
    for candidate in chosen:
        size = entry_size(candidate.entry)
        if len(picked) == MAX_ENTRIES:
            break
        if used + size <= MAX_CHARS:
            picked.append(candidate.entry)
            used += size
    return picked


def select_entries(entries: Sequence[LoreEntry], recent: Sequence[str]) -> list[LoreEntry]:
    """
    카드에 넣을 항목들. entries 는 판의 항목들(로어북의 차례, 그 안의 차례),
    recent 는 최근 말들(오래된 것부터, 이번에 보낸 말까지)이다.
    """
    return within_limits(candidates(entries, scanned_text(recent)))


def render_lore(entries: Sequence[LoreEntry]) -> str | None:
    """'[로어북]' 블록. 항목이 없으면 None."""
    if not entries:
        return None
    return '\n'.join(['[로어북]', *(f'- {entry.name}: {entry.content}' for entry in entries)])
