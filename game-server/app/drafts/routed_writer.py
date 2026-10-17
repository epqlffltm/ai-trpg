# game-server/app/drafts/routed_writer.py

"""
부를 때마다 모델의 이름으로 provider 를 골라(app/ai/routing.py) 장부 초안을 받는 것. Drafter 모양을 따른다.

서술자(app/rounds/routed_narrator.py)와 같은 까닭으로 고르는 일을 부를 때로 미룬다.
고르지 못하면(꺼진 모델, 키 없음) 초안 없이 지나간다(NOTHING). 초안은 덤이다. 까닭은 고르는 쪽이 warning 으로 남긴다.
"""

from dataclasses import dataclass

from app.ai.calls import CallLog
from app.ai.provider import ProviderError
from app.ai.routing import ModelRouter
from app.drafts.validation import NOTHING, Checked
from app.drafts.writer import DraftRequest, DraftWriter


@dataclass(frozen=True)
class RoutedDraftWriter:
    """model 은 설정에 적은 이름이다(standard 등급의 첫 모델)."""

    model: str
    router: ModelRouter
    log: CallLog
    digest_key: bytes | None = None

    async def draft(self, request: DraftRequest) -> Checked:
        """provider 를 고르고, 그것으로 초안을 받는다. 고르지 못하면 NOTHING."""
        try:
            route = await self.router.route(self.model)
        except ProviderError:
            return NOTHING
        writer = DraftWriter(route.provider, self.log, digest_key=self.digest_key, price=route.price)
        return await writer.draft(request)
