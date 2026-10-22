# chat-server/app/core/config.py

"""
chat 서버의 설정. 환경 변수와 chat-server/.env 에서 읽는다.

FastAPI 서버들이 함께 쓰는 칸(DB, 인증 서버, 로그, 수집기)은 공용 코드의 설정(server_core.settings.CoreSettings)에 있다.
여기에는 이 서버의 이름과 기본값, 이 서버만의 칸(asset 서버와 결제 서버의 주소와 서명 비밀, 모델의 창구와 키,
말 한 번의 길이)을 둔다.

비밀값과 환경마다 달라지는 값은 코드에 적지 않는다.
다른 서버의 .env 와 따로 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.
"""

from functools import lru_cache
from typing import ClassVar, Self

from pydantic import Field, SecretStr, model_validator
from server_core.service_auth.signing import MIN_SECRET_LENGTH
from server_core.settings import SCHEMA_PATTERN, CoreSettings


class Settings(CoreSettings):
    """
    설정 값의 목록과 형식. 함께 쓰는 칸은 CoreSettings 에 있다.

    같은 이름의 환경 변수가 있으면 그 값을 쓰고, 없으면 .env 파일, 그것도 없으면 여기 적힌 기본값을 쓴다.
    형식이 맞지 않으면(예: DEBUG=maybe) 서버가 뜨기 전에 오류가 난다.
    """

    # 이 서버의 이름. 로그의 service 칸, span 과 메트릭의 출처다. 규격(docs/observability.md)에 적힌 이름이다
    service_name: ClassVar[str] = 'chat-server'

    # 테이블을 두는 스키마. 테스트는 chat_test 로 바꿔서 개발용 데이터와 섞이지 않게 한다
    db_schema: str = Field(default='chat', pattern=SCHEMA_PATTERN)

    # 이 서버의 이름. 토큰의 대상 목록(aud)에 이 이름이 있어야 받는다.
    # 다른 서버용으로 발급된 토큰을 이 서버에 쓰는 것을 막는다
    jwt_audience: str = 'ai-trpg-chat'

    # asset 서버의 주소. 대화를 시작할 때 캐릭터의 판과 페르소나의 사본을 여기서 가져온다
    # (asset-server 의 /api/v1/asset/service/chat/..., app/assets/client.py). 예: http://127.0.0.1:8006
    # 비우면 부르지 않는다. 그때 대화를 만들려 하면 503 이다(진행 중인 대화는 사본으로 돈다)
    asset_url: str = ''

    # asset 서버에 보내는 요청에 서명하는 비밀(server_core/service_auth/signing.py).
    # asset 서버의 CHAT_SERVER_SECRET 과 같은 값이어야 한다. 32자 이상. 비밀값이다. 로그와 오류에 싣지 않는다
    asset_secret: SecretStr = SecretStr('')

    # asset 서버를 한 번 부르는 시간의 상한(초). 대화를 만드는 사람이 기다리므로 짧게 둔다
    asset_timeout_seconds: float = Field(default=5.0, gt=0, le=30)

    # 결제 서버의 주소. 말 한 번의 값을 여기서 받고(홀드, 확정, 반환), 모델의 값을 가격 목록에서 읽는다(app/billing/).
    # 예: http://127.0.0.1:8003. 비우면 받지 않는다(기본). 그때 모델은 값 없이 보이고 말은 공짜로 돈다
    billing_url: str = ''

    # 결제 서버에 보내는 요청에 서명하는 비밀. 결제 서버의 CHAT_SERVER_SECRET 과 같은 값이어야 한다.
    # 32자 이상. 비밀값이다. 로그와 오류에 싣지 않는다
    billing_secret: SecretStr = SecretStr('')

    # 결제 서버를 한 번 부르는 시간의 상한(초). 말을 보내는 사람이 기다리므로 짧게 둔다. 게임 서버와 같은 기본값이다
    billing_timeout_seconds: float = Field(default=5.0, gt=0, le=10)

    # --- 말 한 번(app/turns/) ---
    # 모델의 창구마다 키와 주소. 이름은 게임 서버와 같다.
    # 키가 없는 창구의 모델은 부르지 않는다(provider_not_configured).
    # 키는 비밀값이다. 로그와 오류에 싣지 않는다. 공급자가 내주는 값이라 tools/fill_env.py 가 만들지 않는다
    openai_api_key: SecretStr = SecretStr('')
    openai_base_url: str = 'https://api.openai.com/v1'
    anthropic_api_key: SecretStr = SecretStr('')
    anthropic_base_url: str = 'https://api.anthropic.com'
    gemini_api_key: SecretStr = SecretStr('')
    gemini_base_url: str = 'https://generativelanguage.googleapis.com'
    zai_api_key: SecretStr = SecretStr('')
    zai_base_url: str = 'https://api.z.ai/api/paas/v4'
    deepinfra_api_key: SecretStr = SecretStr('')
    deepinfra_base_url: str = 'https://api.deepinfra.com/v1/openai'
    # 서버 곁의 모델(Ollama)의 주소. 모델 목록의 local 창구 모델에만 쓴다. 지금 목록에는 없다(베이직 등급 때 켠다)
    llm_base_url: str = 'http://127.0.0.1:11434/v1'

    # 모델을 한 번 부르는 시간의 상한(초). 흘려 받는 답이 다 올 때까지다
    llm_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    # 말 한 번의 답의 길이의 상한(토큰). 가격표의 출력 단계(o0)가 약속하는 길이다
    chat_output_limit: int = Field(default=1024, ge=64, le=8192)
    # 모델에 보내는 지난 말의 양의 상한(글자). 최근 말부터 이만큼 채운다(app/conversation/window.py).
    # 가격표의 입력 단계(i0)가 약속하는 양이다. 토큰이 아니라 글자로 어림한다(한국어는 대략 한 글자가 한 토큰 안팎)
    chat_context_chars: int = Field(default=12000, ge=1000, le=200000)
    # 글의 다양함. 0 에 가까울수록 같은 입력에 비슷한 답이다. 받지 않는 모델에는 보내지 않는다(모델 목록)
    chat_temperature: float = Field(default=0.9, ge=0, le=2)
    # 다음 답 추천. 켜면 답 끝에 선택지 셋을 함께 받는다(app/conversation/suggestions.py).
    # 호출은 늘지 않고 출력이 조금 는다
    chat_suggestions: bool = True
    # 굴리는 요약의 모델(모델 목록의 이름표). 싼 모델을 쓴다. 비우면 요약하지 않는다(app/memory/summarizer.py)
    summary_model: str = ''
    # 창 밖으로 밀려난 말이 마지막 요약 뒤로 이만큼 쌓이면 요약한다
    summary_after_messages: int = Field(default=8, ge=2, le=200)

    @model_validator(mode='after')
    def require_an_asset_secret(self) -> Self:
        """asset 서버를 부르겠다면서 비밀이 없거나 짧으면 뜨지 않는다. asset 서버가 모든 요청을 401 로 거절한다."""
        if self.asset_url.strip() and len(self.asset_secret.get_secret_value()) < MIN_SECRET_LENGTH:
            raise ValueError(f'ASSET_URL 을 적었으면 ASSET_SECRET 을 {MIN_SECRET_LENGTH}자 이상 적어야 합니다')
        return self

    @model_validator(mode='after')
    def require_a_billing_secret(self) -> Self:
        """
        결제 서버를 부르겠다면서 비밀이 없거나 짧으면 뜨지 않는다. 결제 서버가 모든 요청을 401 로 거절한다.

        마이그레이션(compose 의 chat-migrate)은 결제 서버를 부르지 않으므로 주소와 비밀을 함께 비운다.
        """
        if self.billing_url.strip() and len(self.billing_secret.get_secret_value()) < MIN_SECRET_LENGTH:
            raise ValueError(f'BILLING_URL 을 적었으면 BILLING_SECRET 을 {MIN_SECRET_LENGTH}자 이상 적어야 합니다')
        return self


@lru_cache
def get_settings() -> Settings:
    """
    설정을 읽어 돌려준다. 처음 한 번만 읽고 그 뒤로는 같은 객체를 돌려준다.

    요청마다 .env 를 다시 읽지 않는다. 테스트는 이 함수를 거치지 않고 Settings 를 직접 만들어 앱에 넣는다.
    """
    return Settings()
