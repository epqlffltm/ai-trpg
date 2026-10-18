# game-server/app/rounds/picked_narrator.py

"""
라운드의 서술 모델로 서술하는 서술자. Narrator 모양을 따른다.
모델이 없는 라운드(모델을 고르는 규칙 전에 연 라운드)는 서버의 기본 모델(LLM_MODEL)의 서술자로 서술한다.

모델은 라운드를 열 때 굳힌 것이다(request.model). 그 모델의 가격표로 값을 걸어 두었다(app/billing/charges.py).
그래서 그 모델로만 서술한다. 실패해도 다른 모델로 넘어가지 않는다. 같은 모델로 다시 시도하는 것은 된다.
다른 모델로 서술하면 낸 값과 받은 서술이 어긋난다.
끝내 실패하면 라운드는 닫는 중에 머물고 방장이 다시 맡길 수 있다.

모델마다 서술자를 서술할 때 만든다(chain_for). 고를 수 있는 모델은 모델 목록과 결제 서버가 정하므로
앱이 뜰 때 미리 만들 수 없다. 만드는 데 드는 것은 없다(app/rounds/routed_narrator.py).
"""

from collections.abc import Callable
from dataclasses import dataclass

from app.rounds.narrator import NO_PREVIEW, NarrationRequest, Narrator, Preview


@dataclass(frozen=True)
class PickedNarrator:
    """chain_for 는 모델 하나로 서술하는 서술자를 만드는 것, default 는 모델을 고르지 않은 라운드의 서술자다."""

    chain_for: Callable[[str], Narrator]
    default: Narrator

    def narrator_for(self, request: NarrationRequest) -> Narrator:
        """이 요청을 맡을 서술자. 모델이 굳어 있으면 그 모델의 것, 아니면 등급의 것이다."""
        if request.model is None:
            return self.default
        return self.chain_for(request.model)

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        """요청의 모델이나 등급의 서술자에게 서술을 맡긴다."""
        return await self.narrator_for(request).narrate(request, preview)
