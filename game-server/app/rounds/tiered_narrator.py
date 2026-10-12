# game-server/app/rounds/tiered_narrator.py

"""
라운드의 서술 등급(app/rounds/tiers.py)에 맞는 서술자에게 서술을 넘기는 서술자.

등급마다 서술자가 하나씩 있다. 보통은 그 등급의 모델들을 차례로 다시 시도하는 서술자다(app/rounds/retrying_narrator.py).
여기서는 고르기만 한다. 다시 시도하기도, 기록도 안쪽의 서술자가 한다.

등급의 서술자가 없으면 서술하지 않는다(tier_unavailable). 더 싼 등급으로 서술하지 않는다.
그 라운드는 그 등급의 값을 이미 걸어 두었다. 다른 등급으로 서술하면 낸 값과 받은 서술이 어긋난다.
설정에서 등급의 모델을 지운 뒤에 그 등급으로 열린 라운드가 이렇게 된다. 설정을 되돌리고 방장이 다시 맡기면 서술한다.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from app.rounds.llm_narrator import NarrationError
from app.rounds.narrator import NO_PREVIEW, NarrationRequest, Narrator, Preview
from app.rounds.tiers import NarrationTier

# 그 등급의 서술자가 없을 때의 실패의 이유. 앉은 사람 모두에게 narration_failed 로 간다
TIER_UNAVAILABLE = 'tier_unavailable'


@dataclass(frozen=True)
class TieredNarrator:
    """등급마다의 서술자. 요청의 등급(request.tier)으로 고른다."""

    narrators: Mapping[NarrationTier, Narrator]

    def narrator_for(self, tier: NarrationTier) -> Narrator:
        """그 등급의 서술자. 없으면 NarrationError(tier_unavailable)."""
        narrator = self.narrators.get(tier)
        if narrator is None:
            raise NarrationError(TIER_UNAVAILABLE)
        return narrator

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        """요청의 등급의 서술자에게 서술을 맡긴다."""
        return await self.narrator_for(request.tier).narrate(request, preview)
