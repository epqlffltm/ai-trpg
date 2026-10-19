# trpg-server/app/rounds/routed_narrator.py

"""
부를 때마다 모델의 이름으로 provider 를 골라(app/ai/routing.py) 서술하는 서술자. Narrator 모양을 따른다.

서술자를 앱이 뜰 때 한 번 만들면, 모델 목록에서 끄거나 날짜판을 바꾼 것이 서버를 다시 띄울 때까지 맞지 않는다.
그래서 고르는 일을 서술할 때로 미룬다. 고른 provider 로 언어 모델 서술자(LLMNarrator)를 그때 만들어 부른다.
LLMNarrator 는 값 몇 개를 담은 것이라 만드는 데 드는 것이 없다. 부르고 기록하는 일은 그대로 그것이 한다.

고르지 못하면(꺼진 모델, 키 없음) ProviderError 를 그대로 올린다.
다시 시도하는 서술자(app/rounds/retrying_narrator.py)가 그 이유로 그 모델은 다시 부르지 않는다.
부르지 않았으므로 미리 보기도 시작하지 않는다.
"""

from dataclasses import dataclass

from app.ai.calls import CallLog
from app.ai.routing import ModelRouter
from app.rounds.llm_narrator import LLMNarrator
from app.rounds.narrator import NO_PREVIEW, NarrationRequest, Preview


@dataclass(frozen=True)
class RoutedNarrator:
    """model 은 설정에 적은 이름이다. 모델 목록의 이름표이거나 서버 곁의 모델의 이름이다."""

    model: str
    router: ModelRouter
    log: CallLog
    digest_key: bytes | None = None

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        """provider 를 고르고, 그것으로 서술한다. 모델 목록의 모델이면 그날의 단가로 원가를 센다."""
        route = await self.router.route(self.model)
        narrator = LLMNarrator(route.provider, self.log, digest_key=self.digest_key, price=route.price)
        return await narrator.narrate(request, preview)
