# shared/server-core/src/server_core/billing/settings.py

"""
결제 서버를 부르는 서버(게임, chat, story)의 설정 칸. 서버의 설정이 CoreSettings 와 함께 물려받는다.

    class Settings(CoreSettings, BillingSettings):
        ...

주소를 비우면 받지 않는다(기본). 테스트와 결제 서버 없는 개발은 비운 채로 돈다(free_billing.py).
주소를 적었는데 비밀이 짧으면 뜨지 않는다. 뜬 뒤에 결제 서버가 모든 요청을 401 로 거절하는 것보다 낫다.
마이그레이션(compose 의 *-migrate)은 결제 서버를 부르지 않으므로 주소와 비밀을 함께 비운다.
"""

from typing import Self

from pydantic import BaseModel, Field, SecretStr, model_validator

from server_core.service_auth.signing import MIN_SECRET_LENGTH

# 결제 서버를 한 번 부르는 시간의 상한(초)의 상한. 값을 잡는 사람(라운드를 닫는 사람, 말을 보낸 사람)이 기다린다
BILLING_BUDGET_SECONDS = 10.0


class BillingSettings(BaseModel):
    """결제 서버의 주소, 서명 비밀, 시간 상한."""

    # 결제 서버의 주소. 예: http://127.0.0.1:8003. 비우면 받지 않는다(기본).
    # 그때 모델은 값 없이 보이고 값을 받는 일(서술, 말)이 공짜로 돈다
    billing_url: str = ''

    # 결제 서버에 보내는 요청에 서명하는 비밀. 결제 서버의 <이 서버>_SERVER_SECRET(GAME_SERVER_SECRET,
    # CHAT_SERVER_SECRET, STORY_SERVER_SECRET)과 같은 값이어야 한다. 32자 이상. 비밀값이다. 로그와 오류에 싣지 않는다
    billing_secret: SecretStr = SecretStr('')

    # 결제 서버를 한 번 부르는 시간의 상한(초)
    billing_timeout_seconds: float = Field(default=5.0, gt=0, le=BILLING_BUDGET_SECONDS)

    @model_validator(mode='after')
    def require_a_billing_secret(self) -> Self:
        """결제 서버를 부르겠다면서 비밀이 없거나 짧으면 뜨지 않는다. 결제 서버가 모든 요청을 401 로 거절한다."""
        if self.billing_url.strip() and len(self.billing_secret.get_secret_value()) < MIN_SECRET_LENGTH:
            raise ValueError(f'BILLING_URL 을 적었으면 BILLING_SECRET 을 {MIN_SECRET_LENGTH}자 이상 적어야 합니다')
        return self
