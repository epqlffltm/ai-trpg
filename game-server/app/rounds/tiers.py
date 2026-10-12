# game-server/app/rounds/tiers.py

"""
서술 등급. 어느 모델들로 서술하고, 서술 한 번에 얼마를 받는가를 함께 정하는 이름이다(#151 의 게임 서버 몫).

  - 방장이 테이블마다 고른다(app/tables/tiers.py). 바꾸면 다음 라운드부터다.
  - 라운드를 열 때 그 라운드의 등급으로 굳는다(app/rounds/opener.py). 그 등급의 값을 건다(app/billing/charges.py).
  - 라운드를 서술할 때 그 등급의 모델들을 부른다(app/rounds/tiered_narrator.py).
    한 등급 안에서 다음 모델로 넘어가도 값은 그대로다. 등급을 넘어 넘어가지는 않는다.

등급마다 어느 모델을 쓸지는 서버의 설정이 정한다(app/rounds/narrator_setup.py 의 tier_models).
값은 결제 서버의 가격표가 정한다(narration.<등급>). 게임 서버는 금액을 모른다.

다른 것을 불러오지 않는다. 테이블, 라운드, 청구의 모델이 모두 이것을 쓴다.
"""

import enum


class NarrationTier(enum.StrEnum):
    """서술 등급. 값이 결제 서버의 가격표 이름의 뒷부분이 된다(narration.standard)."""

    # 기본. 서버의 첫 모델(LLM_MODEL)과 넘어갈 모델들
    STANDARD = 'standard'
    # 더 좋은 모델. 서버가 따로 적어 둔 모델이 있어야 고를 수 있다(LLM_PREMIUM_MODEL)
    PREMIUM = 'premium'
