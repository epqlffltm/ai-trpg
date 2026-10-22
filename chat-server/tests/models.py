# chat-server/tests/models.py

"""
테스트가 모델을 부르는 자리에 끼우는 가짜(app.state.model_router). 진짜 공급자를 부르지 않는다.

  - ScriptedProvider: 정해 둔 조각을 흘려 주고, 정해 둔 대로 끝난다(다 씀, 잘림, 도중에 실패, 멈춰 기다림).
    받은 메시지를 적어 둔다. 테스트가 "모델에게 무엇을 보냈나"를 본다.
  - FakeRouter: 이름표마다 그 provider 를 돌려준다. refuse 를 주면 ProviderError 로 고르지 못한다.
"""

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal

from ai_core.catalog_contract import UnitCost
from ai_core.costs import PriceTag
from ai_core.provider import ChatMessage, Completion, GenerationParams, ProviderError, TextSink, ignore_text
from ai_core.routing import Route

# 테스트 모델의 단가(USD, 백만 토큰당)
TEST_COST = UnitCost(cost_id=1, input_per_mtok=Decimal('1'), output_per_mtok=Decimal('5'))


@dataclass
class ScriptedProvider:
    """
    정해 둔 대로 답하는 provider.

    pieces 를 차례로 흘려 준 뒤, error 가 있으면 그것을 올리고, 없으면 이어 붙인 글을 돌려준다.
    hold 가 있으면 조각을 흘린 뒤 그것이 켜질 때까지 기다린다(멈추기와 끊김을 시험한다).
    """

    kind = 'fake'
    model = 'scripted'

    pieces: list[str] = field(default_factory=lambda: ['어서 ', '와요.'])
    error: ProviderError | None = None
    truncated: bool = False
    input_tokens: int | None = 1000
    output_tokens: int | None = 200
    hold: asyncio.Event | None = None
    calls: list[tuple[list[ChatMessage], GenerationParams]] = field(default_factory=list)

    async def complete(
        self, messages: list[ChatMessage], params: GenerationParams, on_text: TextSink = ignore_text
    ) -> Completion:
        self.calls.append((list(messages), params))
        for piece in self.pieces:
            on_text(piece)
            await asyncio.sleep(0)
        if self.hold is not None:
            await self.hold.wait()
        if self.error is not None:
            raise self.error
        return Completion(
            text=''.join(self.pieces),
            model=self.model,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            truncated=self.truncated,
        )


@dataclass
class FakeRouter:
    """이름표마다 provider 를 고르는 가짜. refuse 가 있으면 고르지 못한다(ProviderError(refuse))."""

    provider: ScriptedProvider = field(default_factory=ScriptedProvider)
    refuse: str | None = None
    routed: list[str] = field(default_factory=list)

    async def route(self, name: str, allow_disabled: bool = False) -> Route:
        self.routed.append(name)
        if self.refuse is not None:
            raise ProviderError(self.refuse)
        return Route(self.provider, PriceTag(name, TEST_COST))
