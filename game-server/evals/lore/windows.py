# game-server/evals/lore/windows.py

"""
키워드가 나온 문장을 떼어 낸다. 키워드로 걸린 항목이 정말 그 뜻인지 문장 하나의 뜻으로 견주려고 쓴다.

질의 전체(장면 + 선언)의 벡터로 견주면 장면이 길 때 키워드가 든 한 문장의 뜻이 묻힌다.
"이번 계획을 망치고 싶지 않다" 한 문장만 떼어 내면 드워프 정비공(키워드 망치)의 글과 멀다는 것이 더 잘 드러난다.

평가에서 먼저 잰다. 서버에 넣기로 하면 app/lore 로 옮긴다.
"""

import re

from app.assets.scenarios.snapshot import EntrySnapshot
from app.lore.retrieval import mentions

# 문장의 끝. 마침표, 물음표, 느낌표, 말줄임표 뒤의 공백과 줄바꿈에서 자른다
SENTENCE_END = re.compile(r'(?<=[.!?…])\s+|\n+')


def sentences(text: str) -> list[str]:
    """글을 문장들로. 빈 문장은 뺀다."""
    return [part.strip() for part in SENTENCE_END.split(text) if part.strip()]


def windows_for(entry: EntrySnapshot, text: str) -> list[str]:
    """항목의 이름이나 키워드가 나온 문장들. 한 문장에 다 들지 않으면(문장 경계에 걸침) 글 전체 하나."""
    found = [sentence for sentence in sentences(text) if mentions(entry, sentence)]
    return found or [text]
