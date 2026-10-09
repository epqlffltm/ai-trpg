# game-server/app/ai/fake.py

"""
가짜 provider. 모델을 부르지 않고 정해 둔 글을 돌려준다.

자동 테스트(CI 포함)는 이것만 쓴다. 실제 모델은 느리고, 돈이 들고, 같은 입력에 같은 글을 내지 않는다.
받은 것을 적어 두어서, 테스트가 "모델에게 무엇을 보냈나"를 들여다볼 수 있다.
"""

from dataclasses import dataclass, field

from app.ai.provider import ChatMessage, Completion, GenerationParams

# 가짜 모델의 이름. 기록에 남을 때 진짜 모델과 섞이지 않게 한다
FAKE_MODEL = 'fake'


@dataclass(frozen=True)
class Call:
    """가짜 provider 가 받은 요청 하나."""

    messages: list[ChatMessage]
    params: GenerationParams


@dataclass
class FakeProvider:
    """
    정해 둔 글을 돌려주는 provider. 몇 번을 불러도 같은 글이다.

    reply 가 돌려줄 글이다. calls 에 받은 요청이 쌓인다.
    """

    reply: str = '바람이 분다.'
    calls: list[Call] = field(default_factory=list)

    async def complete(self, messages: list[ChatMessage], params: GenerationParams) -> Completion:
        """받은 것을 적어 두고 정해 둔 글을 돌려준다."""
        self.calls.append(Call(messages=list(messages), params=params))
        return Completion(text=self.reply, model=FAKE_MODEL)
