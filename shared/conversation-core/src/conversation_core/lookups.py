# shared/conversation-core/src/conversation_core/lookups.py

"""
모델을 부르기 직전에 카드에 더하는 두 찾기(chat, story). 로어북을 뜻으로 찾기(#672), 그다음 참고 자료(#1338).
DB 도 모델도 모른다. 찾는 일은 서버가 넘긴 것(recall, finder)이 하고, 카드의 어디에 넣는지도 서버가 넘긴다.

  1. 로어북: 상시와 키워드로 고른 것(plan.ranked) 뒤에 뜻으로 찾은 것을 붙여 다시 고른다. 카드의 "[로어북]" 을 바꾸고,
     말 한 번의 바탕(plan)의 블록과 글자도 바꾼다
  2. 참고 자료: 제작자의 로어북이 먼저다. 로어북의 상한(MAX_CHARS)에서 로어북이 쓰고 남은 글자만 넘긴다.
     찾는 글이 없으면(판이 허용하지 않았거나 사람이 켜지 않았다) 찾지 않는다
찾지 못했거나 더할 것이 없으면 말 한 번은 그대로다. 실패를 감싸는 것(시간 상한, 로그)은 넘긴 쪽의 일이다.

말 한 번(start)과 그 바탕(plan)은 서버의 frozen dataclass 다. 여기서는 쓰는 칸의 모양(Protocol)만 안다.
"""

import dataclasses
from collections.abc import Callable, Sequence
from typing import Any, Protocol, cast

from conversation_core.lorebook import MAX_CHARS, LoreEntry, chosen_entries, entry_size, render_lore, with_recalled


class CardMessage(Protocol):
    """모델에 보내는 메시지 하나. 맨 앞의 것이 카드다."""

    @property
    def content(self) -> str: ...


class LoreBasis(Protocol):
    """
    로어북을 뜻으로 찾아 더할 바탕. entries 는 판의 항목, ranked 는 상시와 키워드로 고른 자리들,
    block 은 카드에 넣은 "[로어북]"(없으면 None), chars 는 그 블록에 든 항목의 글자의 합이다.
    """

    @property
    def entries(self) -> Sequence[LoreEntry]: ...

    @property
    def ranked(self) -> Sequence[int]: ...

    @property
    def block(self) -> str | None: ...

    @property
    def chars(self) -> int: ...


class LookupTurn(Protocol):
    """말 한 번에서 두 찾기가 읽고 바꾸는 칸. references 는 참고 자료를 찾는 글이다(끄면 None)."""

    @property
    def messages(self) -> Sequence[CardMessage]: ...

    @property
    def lore(self) -> LoreBasis | None: ...

    @property
    def references(self) -> str | None: ...


class LoreRecaller(Protocol):
    """로어북을 뜻으로 찾는 것(서버의 app/lore/recall.py). 찾은 항목의 자리들. 실패하면 빈 목록이다."""

    async def recall(self, plan: Any) -> list[int]: ...


class ReferenceBlocks(Protocol):
    """참고 자료를 찾아 블록으로 주는 것(reference_core/finder.py). 자리가 없거나 찾지 못하면 None 이다."""

    async def block_after(self, text: str, used: int, budget: int) -> str | None: ...


def lore_chars(entries: Sequence[LoreEntry]) -> int:
    """카드에 넣은 로어북 항목의 글자(이름과 내용)의 합. 참고 자료의 자리를 셈하는 바탕이다."""
    return sum(entry_size(entry) for entry in entries)


def with_card[T: LookupTurn](start: T, content: str) -> T:
    """카드(맨 앞의 메시지)의 글을 바꾼 말 한 번. 나머지 메시지는 그대로다."""
    card, *rest = start.messages
    rebuilt = dataclasses.replace(cast(Any, card), content=content)
    return cast(T, dataclasses.replace(cast(Any, start), messages=[rebuilt, *rest]))


async def with_recalled_lore[T: LookupTurn](
    recall: LoreRecaller | None, start: T, swap: Callable[[str, str | None, str | None], str]
) -> T:
    """
    로어북을 뜻으로 찾아 카드의 "[로어북]" 에 더한다. swap(카드, 옛 블록, 새 블록)은 서버의 카드에서 블록을 바꾼다.
    찾을 수 없거나 더할 것이 없으면 그대로다.
    """
    plan = start.lore
    if recall is None or plan is None:
        return start
    recalled = await recall.recall(plan)
    if not recalled:
        return start
    chosen = chosen_entries(plan.entries, with_recalled(plan.ranked, recalled))
    block = render_lore(chosen)
    lore = dataclasses.replace(cast(Any, plan), block=block, chars=lore_chars(chosen))
    changed = with_card(start, swap(start.messages[0].content, plan.block, block))
    return cast(T, dataclasses.replace(cast(Any, changed), lore=lore))


async def with_found_references[T: LookupTurn](
    finder: ReferenceBlocks | None, start: T, insert: Callable[[str, str], str]
) -> T:
    """
    참고 자료를 찾아 카드에 넣는다(로어북을 바꾼 뒤에 부른다). insert(카드, 블록)는 서버의 카드에 블록을 넣는다.
    끄거나, 자리가 없거나, 찾지 못했으면 그대로다.
    """
    if finder is None or start.references is None:
        return start
    used = start.lore.chars if start.lore is not None else 0
    block = await finder.block_after(start.references, used, MAX_CHARS)
    if block is None:
        return start
    return with_card(start, insert(start.messages[0].content, block))
