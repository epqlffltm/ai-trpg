# game-server/app/ai/fake.py

"""
가짜 provider 와 가짜 임베더. 모델을 부르지 않고 정해 둔 글, 글에서 바로 계산한 벡터를 돌려준다.

자동 테스트(CI 포함)는 이것만 쓴다. 실제 모델은 느리고, 돈이 들고, 같은 입력에 같은 글을 내지 않는다.
받은 것을 적어 두어서, 테스트가 "모델에게 무엇을 보냈나"를 들여다볼 수 있다.
진짜 provider 처럼 글을 몇 글자씩 조각내어 흘려 준다. 조각을 받는 쪽을 테스트할 수 있다.
"""

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import ClassVar

from app.ai.calls import CallRecord
from app.ai.provider import ChatMessage, Completion, GenerationParams, ProviderError, TextSink, ignore_text

# 가짜 모델의 이름. 기록에 남을 때 진짜 모델과 섞이지 않게 한다
FAKE_MODEL = 'fake'

# 흘려 줄 때 한 조각의 글자 수
PIECE_SIZE = 4

# 가짜 임베더의 벡터 길이. 진짜(bge-m3 는 1024)보다 짧다. 테스트에서 낱말이 겹치는지만 드러나면 된다
FAKE_DIMENSIONS = 64

# 낱말을 가르는 것. 글자와 숫자가 아닌 것(공백, 문장 부호)에서 자른다
WORD_PATTERN = re.compile(r'\w+')


@dataclass(frozen=True)
class Call:
    """가짜 provider 가 받은 요청 하나."""

    messages: list[ChatMessage]
    params: GenerationParams


def split_text(text: str, size: int) -> list[str]:
    """글을 size 글자씩 자른다. 이어 붙이면 원래 글이다. 빈 글이면 빈 목록이다."""
    return [text[start : start + size] for start in range(0, len(text), size)]


@dataclass
class FakeProvider:
    """
    정해 둔 글을 돌려주는 provider. 몇 번을 불러도 같은 글이다.

    reply 가 돌려줄 글이다. truncated 를 켜면 길이 상한에 걸려 끊긴 답을 흉내 낸다. calls 에 받은 요청이 쌓인다.
    piece_size 글자씩 조각내어 on_text 에 넘긴 뒤에 답을 돌려준다.
    """

    kind: ClassVar[str] = 'fake'

    reply: str = '바람이 분다.'
    truncated: bool = False
    model: str = FAKE_MODEL
    piece_size: int = PIECE_SIZE
    calls: list[Call] = field(default_factory=list)

    async def complete(
        self, messages: list[ChatMessage], params: GenerationParams, on_text: TextSink = ignore_text
    ) -> Completion:
        """받은 것을 적어 두고, 정해 둔 글을 조각내어 흘려 준 뒤 돌려준다."""
        self.calls.append(Call(messages=list(messages), params=params))
        for piece in split_text(self.reply, self.piece_size):
            on_text(piece)
        return Completion(text=self.reply, model=self.model, truncated=self.truncated)


def word_slot(word: str) -> int:
    """낱말이 벡터의 몇 번째 칸에 들어가는가. 같은 낱말은 늘 같은 칸이다(파이썬의 hash 는 실행마다 달라 쓰지 않는다)."""
    digest = hashlib.blake2b(word.casefold().encode(), digest_size=4).digest()
    return int.from_bytes(digest) % FAKE_DIMENSIONS


def word_vector(text: str) -> list[float]:
    """
    글의 낱말을 칸마다 세고 길이를 1 로 맞춘 벡터. 낱말이 많이 겹치는 글끼리 가깝다.

    낱말이 하나도 없으면 첫 칸만 1 인 벡터다. 길이가 0 인 벡터는 거리를 잴 수 없다.
    """
    counts = [0.0] * FAKE_DIMENSIONS
    for word in WORD_PATTERN.findall(text):
        counts[word_slot(word)] += 1.0
    norm = math.sqrt(sum(count * count for count in counts))
    if norm == 0:
        return [1.0] + [0.0] * (FAKE_DIMENSIONS - 1)
    return [count / norm for count in counts]


@dataclass
class FakeEmbedder:
    """
    글에서 바로 계산한 벡터를 돌려주는 임베더. 같은 글은 늘 같은 벡터다.

    뜻은 모르고 낱말이 겹치는지만 본다. 검색이 "가까운 것을 먼저" 고르는지 테스트하기에는 충분하다.
    error 를 두면 부를 때마다 그 이유로 실패한다. calls 에 받은 글의 목록이 쌓인다.
    """

    kind: ClassVar[str] = 'fake'

    model: str = FAKE_MODEL
    error: str | None = None
    calls: list[list[str]] = field(default_factory=list)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """받은 것을 적어 두고 글마다 벡터를 돌려준다."""
        self.calls.append(list(texts))
        if self.error is not None:
            raise ProviderError(self.error)
        return [word_vector(text) for text in texts]


@dataclass
class FakeCallLog:
    """받은 호출 기록을 목록에 쌓아 두는 기록장. DB 에 쓰지 않는다. 테스트가 무엇이 기록됐는지 들여다본다."""

    records: list[CallRecord] = field(default_factory=list)

    async def write(self, record: CallRecord) -> None:
        """기록 하나를 쌓는다."""
        self.records.append(record)
