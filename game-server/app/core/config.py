# game-server/app/core/config.py

"""
게임 서버의 설정. 환경 변수와 game-server/.env 에서 읽는다.

비밀값과 환경마다 달라지는 값은 코드에 적지 않는다.
인증 서버의 .env 와 따로 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 서술 하나에 쓰는 시간의 상한(초). 다시 시도하기와 다음 모델로 넘어가기를 모두 이 안에서 한다
# (app/rounds/retrying_narrator.py).
# 한 번 부르는 시간(LLM_TIMEOUT_SECONDS)은 이보다 길 수 없다. 길면 첫 시도만으로 상한을 넘는다
NARRATION_BUDGET_SECONDS = 150.0

# 서술하기 전에 결제 서버에서 크레딧을 확보하는 데 쓰는 시간의 상한(초). 서술을 맡은 작업의 시간에 들어간다.
# 한 번 부르는 시간(BILLING_TIMEOUT_SECONDS)은 이보다 길 수 없다
BILLING_BUDGET_SECONDS = 10.0

# 결제 서버의 비밀의 가장 짧은 길이. 결제 서버(GAME_SERVER_SECRET)와 같은 기준이다
BILLING_SECRET_MIN_LENGTH = 32

# 실시간 신호에 서명하는 비밀의 가장 짧은 길이
SIGNAL_SECRET_MIN_LENGTH = 32

# 인증 서버의 두 주소의 끝. 둘은 같은 곳(/api/v1/auth)에 있다
JWKS_PATH = '/jwks'
SESSION_REVOCATIONS_PATH = '/session-revocations'


def model_chain(first: str, fallbacks: str) -> list[str]:
    """첫 모델과 쉼표로 나눈 넘어갈 모델들을 부를 차례대로 늘어놓는다. 빈 이름과 앞뒤 공백은 뺀다."""
    names = [name.strip() for name in fallbacks.split(',')]
    return [first.strip(), *(name for name in names if name)]


class Settings(BaseSettings):
    """
    설정 값의 목록과 형식.

    같은 이름의 환경 변수가 있으면 그 값을 쓰고, 없으면 .env 파일, 그것도 없으면 여기 적힌 기본값을 쓴다.
    형식이 맞지 않으면(예: DEBUG=maybe) 서버가 뜨기 전에 오류가 난다.
    """

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        # .env 에 이 서버가 모르는 값이 있어도 무시한다
        extra='ignore',
        # 설정이 틀렸을 때의 오류 메시지에 읽은 값을 싣지 않는다.
        # 싣게 두면 비밀번호가 든 주소나 .env 의 다른 값이 화면과 로그에 찍힌다
        hide_input_in_errors=True,
    )

    # 이 서버가 도는 환경의 이름. 로그의 environment 칸에 들어간다(docs/observability.md).
    # development, test, staging, production 처럼 적는다. 동작을 바꾸지 않는다. 기록을 가를 때만 쓴다
    app_environment: str = Field(default='development', pattern=r'^[a-z][a-z0-9_-]{0,31}$')

    # 이 서버의 버전. 로그의 version 칸에 들어간다. 배포할 때 git SHA 나 이미지의 버전을 넣는다.
    # 적지 않으면 dev 다. 어느 코드가 남긴 기록인지 가를 때 쓴다
    app_version: str = Field(default='dev', pattern=r'^[A-Za-z0-9._+-]{1,64}$')

    # 이 수준부터 로그를 남긴다. debug, info, warning, error 중 하나다
    log_level: Literal['debug', 'info', 'warning', 'error'] = 'info'

    # 개발용 기능(API 문서 화면)을 켠다. 기본은 꺼짐이다.
    # 켜는 것을 잊으면 불편할 뿐이지만, 끄는 것을 잊으면 운영 서버의 API 구조가 드러난다
    debug: bool = False

    # DB 접속 주소. 기본값이 없다. 적지 않으면 서버가 뜨지 않는다.
    # 예: postgresql+asyncpg://game:비밀번호@127.0.0.1:5432/trpg
    database_url: str

    # 테이블을 두는 스키마. 테스트는 game_test 로 바꿔서 개발용 데이터와 섞이지 않게 한다
    db_schema: str = 'game'

    # 인증 서버가 공개키를 내주는 주소(JWKS). 기본값이 없다.
    # 여기서 받은 키로 서명된 토큰을 믿는다. 엉뚱한 주소를 기본으로 믿는 것보다 뜨지 않는 쪽이 낫다.
    # 예: http://127.0.0.1:8000/api/v1/auth/jwks
    auth_jwks_url: str

    # 인증 서버가 끊긴 세션의 목록을 내주는 주소(#274). 비우면 AUTH_JWKS_URL 옆(…/session-revocations)이다.
    # AUTH_JWKS_URL 이 /jwks 로 끝나지 않으면 적어야 한다. 쓰는 곳은 session_revocations_url 이다
    auth_session_revocations_url: str = ''

    # 토큰을 발급한 서버의 이름(iss). 인증 서버의 JWT_ISSUER 와 같아야 한다
    jwt_issuer: str = 'ai-trpg-auth'

    # 이 서버의 이름. 토큰의 대상 목록(aud)에 이 이름이 있어야 받는다.
    # 다른 서버용으로 발급된 토큰을 이 서버에 쓰는 것을 막는다
    jwt_audience: str = 'ai-trpg-game'

    # GM 의 서술을 누가 쓰나. fake 는 AI 를 부르지 않는 가짜(기본), llm 은 언어 모델.
    # 기본을 가짜로 둔다. 테스트와 CI 는 모델 없이 돈다. 실제 모델은 각자의 .env 에서 켠다
    narrator: Literal['fake', 'llm'] = 'fake'

    # 언어 모델을 부르는 주소. OpenAI 와 같은 모양이고 /chat/completions 앞까지 적는다.
    # 기본은 같은 PC 의 Ollama 다. Ollama 는 인증이 없으므로 같은 PC(127.0.0.1) 밖으로 열지 않는다
    llm_base_url: str = 'http://127.0.0.1:11434/v1'

    # 모델의 이름. narrator=llm 이면 반드시 적는다(예: gemma4:26b).
    # 모델 목록(app/catalog, scripts/models.py)의 이름표를 적으면 목록의 창구와 날짜판으로 부른다(예: gpt-6-luna).
    # 목록에 없는 이름이면 LLM_BASE_URL 의 그 모델을 부른다. 아래의 넘어갈 모델도 같다.
    # 서술은 테이블의 서술 모델로 한다. 이것은 서술 모델이 없는 옛 라운드와 장부 초안의 기본이다
    llm_model: str = ''

    # 첫 모델이 끝내 실패하면 차례로 넘어갈 모델들. 쉼표로 나눠 적는다(예: gemma4:31b-it-qat,qwen3.6:27b).
    # 비우면 넘어가지 않는다(기본). 같은 주소(LLM_BASE_URL)의 모델들이다
    llm_fallback_models: str = ''

    # 장부 초안(app/drafts/)을 쓰는 모델. 적는 법은 LLM_MODEL 과 같다. 비우면 LLM_MODEL 이다.
    # 장부 초안은 청구하지 않는 호출이라 원가가 모두 우리 몫이다. 고르는 일이라 싼 모델(Flash 급)이면 충분하다
    draft_model: str = ''

    # 모델의 답을 한 번 기다리는 시간(초). 처음 부를 때는 모델을 메모리에 올리느라 수십 초가 걸린다.
    # 서술은 요청과 따로 도는 작업이라 플레이어의 요청이 이만큼 기다리지는 않는다.
    # 서술 하나의 상한(NARRATION_BUDGET_SECONDS)보다 길 수 없다
    llm_timeout_seconds: float = Field(default=60.0, gt=0, le=NARRATION_BUDGET_SECONDS)

    # 모델이 추론 수준(reasoning_effort)을 아는가. 알면 늘 보내서 기본으로 추론을 끈다.
    # 모르는 모델에 보냈다가 오류가 나면 false 로 바꾼다. 모델 목록의 모델은 목록에 적은 것을 따른다
    llm_supports_reasoning: bool = True

    # OpenAI 의 API 키. 비우면 모델 목록의 openai 창구 모델을 부르지 않는다(그 서술은 provider_not_configured).
    # 비밀값이다. .env 에만 적는다. 로그, 오류, 호출 기록에 싣지 않는다.
    # 키에 월 사용 한도를 걸어 둔다(OpenAI 의 Limits 화면)
    openai_api_key: SecretStr = SecretStr('')
    # OpenAI 의 API 주소. /chat/completions 앞까지다. 바꿀 일이 거의 없다
    openai_base_url: str = 'https://api.openai.com/v1'

    # Anthropic(Claude)의 API 키. 비우면 모델 목록의 anthropic 창구 모델을 부르지 않는다(provider_not_configured).
    # 비밀값이다. .env 에만 적는다. 로그, 오류, 호출 기록에 싣지 않는다. 키에 월 사용 한도를 걸어 둔다
    anthropic_api_key: SecretStr = SecretStr('')
    # Anthropic 의 API 주소. /v1/messages 앞까지다. 바꿀 일이 거의 없다
    anthropic_base_url: str = 'https://api.anthropic.com'

    # Google(Gemini)의 API 키. 비우면 모델 목록의 gemini 창구 모델을 부르지 않는다(provider_not_configured).
    # 비밀값이다. .env 에만 적는다. 로그, 오류, 호출 기록에 싣지 않는다. 주소가 아니라 머리(x-goog-api-key)로 보낸다
    gemini_api_key: SecretStr = SecretStr('')
    # Gemini 의 API 주소. /v1beta 앞까지다. 바꿀 일이 거의 없다
    gemini_base_url: str = 'https://generativelanguage.googleapis.com'

    # Z.ai(GLM)의 API 키. 비우면 모델 목록의 zai 창구 모델을 부르지 않는다(provider_not_configured).
    # 비밀값이다. .env 에만 적는다. 로그, 오류, 호출 기록에 싣지 않는다.
    # 사용자의 글이 국외(싱가포르)에서 처리된다. 파는 모델로 열기 전에 국외 이전을 안내한다
    zai_api_key: SecretStr = SecretStr('')
    # Z.ai 의 API 주소. /chat/completions 앞까지다. 코딩 요금제의 주소(/api/coding/...)가 아니라 일반 API 의 주소다
    zai_base_url: str = 'https://api.z.ai/api/paas/v4'

    # 서술을 동시에 몇 개까지 돌리나(app/core/jobs.py, #275). 넘는 것은 차례를 기다린다.
    # 모델이 한 번에 받는 수(Ollama 의 OLLAMA_NUM_PARALLEL, 외부 API 의 속도 제한)에 맞춘다.
    # 기다리는 시간도 서술 하나의 시간(닫기 시작한 때부터)에 들어간다. 너무 작으면 몰릴 때 시간 초과가 난다
    job_narration_concurrency: int = Field(default=4, ge=1, le=64)

    # 색인(로어북, 기억)을 종류마다 동시에 몇 개까지 돌리나. 임베딩 모델을 서술과 함께 쓰므로 작게 둔다
    job_index_concurrency: int = Field(default=2, ge=1, le=16)

    # AI 호출의 기록(ai_invocations)에 남은 원문(모델이 쓴 글)을 며칠 두나(app/ai/retention.py, #274).
    # 지나면 원문만 비우고 모델, 토큰 수, 걸린 시간 같은 것은 남긴다
    ai_log_text_retention_days: int = Field(default=30, ge=1, le=3650)

    # 로어북 항목을 벡터로 바꾸는 것(임베딩)을 누가 하나. fake 는 모델을 부르지 않는 가짜(기본), llm 은 임베딩 모델.
    # 서술(NARRATOR)과 따로 켠다. 테스트와 CI 는 늘 가짜다
    embedder: Literal['fake', 'llm'] = 'fake'

    # 임베딩 모델의 이름. 한국어를 포함한 여러 언어를 다루는 모델이다(Ollama 에서 ollama pull bge-m3).
    # 바꾸면 벡터를 다시 만들어야 한다. 모델마다 벡터의 공간이 다르다(scripts/index_lore.py)
    embedding_model: str = 'bge-m3'

    # 임베딩 모델을 부르는 주소. OpenAI 와 같은 모양이고 /embeddings 앞까지 적는다. 비우면 LLM_BASE_URL 을 쓴다
    embedding_base_url: str = ''

    # 임베딩을 한 번 기다리는 시간(초). 항목 몇십 개를 한 번에 보낸다
    embedding_timeout_seconds: float = Field(default=30.0, gt=0)

    # 임베딩 모델이 내는 벡터의 길이(차원). 적으면 길이가 다른 답을 받지 않는다(bge-m3 는 1024).
    # 적지 않으면(기본) 보지 않는다. 벡터의 칸은 차원을 정해 두지 않아서 길이가 다른 벡터도 저장은 되고,
    # 거리를 잴 때에야 DB 가 오류를 낸다. 같은 이름의 모델이 다른 길이를 내기 시작하는 것을 여기서 막는다
    embedding_dimensions: int | None = Field(default=None, gt=0)

    # 로어북 검색의 거리 기준(코사인 거리). 모델마다 거리의 크기가 달라서 임베딩 모델을 바꾸면 다시 잰다
    # (uv run python -m scripts.eval_lore). 기본값은 bge-m3 로 잰 것이다(app/lore/retrieval.py 의 같은 이름의 상수).
    # 뜻으로 고를 때: 이보다 먼 항목은 넣지 않는다
    lore_max_distance: float = Field(default=0.45, gt=0, le=2)
    # 키워드로 걸린 항목: 이보다 멀면 넣지 않는다(동음이의어 막기). 임베딩이 실패하면 보지 않는다
    lore_keyword_max_distance: float = Field(default=0.50, gt=0, le=2)

    # 지난 일(앞 라운드의 기억) 검색의 거리 기준(코사인 거리). 기억은 로어북 항목보다 글이 길어 따로 잰다
    # (uv run python -m scripts.eval_memory). 기본값은 bge-m3 로 잰 것이다(app/memory/retrieval.py 의 같은 이름의 상수).
    # 뜻으로 고를 때: 이보다 먼 기억은 넣지 않는다
    memory_max_distance: float = Field(default=0.40, gt=0, le=2)
    # 장면에 나온 인물로 걸린 기억: 이보다 멀면 넣지 않는다. 임베딩이 실패하면 보지 않는다
    memory_keyword_max_distance: float = Field(default=0.50, gt=0, le=2)

    # AI 호출의 기록에 남기는 입력 지문(HMAC)의 키. 비우면 지문을 남기지 않는다.
    # 비밀값이다. 이 키를 아는 사람은 지문으로 입력의 내용을 대입해 맞춰 볼 수 있다.
    # 만들기: uv run python -c "import secrets; print(secrets.token_hex(32))"
    ai_log_hmac_key: SecretStr = SecretStr('')

    # 실시간 신호(NOTIFY)에 서명하는 비밀(app/realtime/signing.py, #75). 32자 이상.
    # 같은 DB 에 붙은 다른 계정이 신호를 꾸며 보내도 서명이 맞지 않아 버린다.
    # 비우면 서버가 뜰 때마다 무작위로 만든다. 서버가 하나면 그대로 된다.
    # 여럿이면 같은 값을 적는다. 다르면 서로의 신호를 버려서, 스트림이 15초마다 스스로 읽을 때에야 따라잡는다.
    # 비밀값이다. 만들기: uv run python -c "import secrets; print(secrets.token_hex(32))"
    signal_secret: SecretStr = SecretStr('')

    # 결제 서버의 주소. 라운드의 서술 값을 여기서 받는다(app/billing/). 비우면 받지 않는다(기본).
    # 테스트와 결제 서버 없는 개발은 비운 채로 돈다. 예: http://127.0.0.1:8003
    billing_url: str = ''

    # 결제 서버에 보내는 요청에 서명하는 비밀. 결제 서버의 GAME_SERVER_SECRET 과 같은 값이어야 한다. 32자 이상.
    # 비밀값이다. 로그와 오류에 싣지 않는다
    billing_secret: SecretStr = SecretStr('')

    # 결제 서버를 한 번 부르는 시간의 상한(초)
    billing_timeout_seconds: float = Field(default=5.0, gt=0, le=BILLING_BUDGET_SECONDS)

    # 시도 횟수 제한(app/limits/, #56)을 세는 Redis 의 주소(redis://...). 비우면 서버 안의 메모리로 센다(기본).
    # 메모리는 서버가 하나일 때만 맞고 다시 띄우면 지워진다. 서버를 여럿 띄우거나 운영에서는 적는다.
    # 인증 서버와 같은 Redis 를 써도 된다. 키의 앞부분(LIMIT_KEY_PREFIX)이 달라 섞이지 않는다
    redis_url: str = ''
    # Redis 에 연결하고 한 명령을 기다리는 시간(초). 요청이 그만큼 기다리므로 짧게 둔다
    redis_timeout_seconds: float = Field(default=0.5, gt=0, le=5)
    # 시도 횟수 제한을 켜는가. 끄면 세지도 막지도 않는다. 테스트가 끈다(제한을 보는 테스트만 켠다)
    limits_enabled: bool = True
    # Redis 의 키의 앞부분. 다른 서버, 테스트와 섞이지 않게 한다
    limit_key_prefix: str = 'game:limit'
    # 로비에서 비밀번호로 들어올 때 틀릴 수 있는 횟수. 한 사람이 한 테이블에, 그리고 테이블 하나에 모든 사람을 합쳐.
    # 구간(PASSWORD_ATTEMPT_WINDOW_SECONDS) 안에 이만큼 틀리면 맞는 비밀번호도 받지 않는다. 맞히면 그 사람의 수는 지운다
    password_attempts_per_user: int = Field(default=5, ge=1)
    password_attempts_per_table: int = Field(default=30, ge=1)
    password_attempt_window_seconds: int = Field(default=600, ge=1)
    # 한 사람이 한 테이블에 구간(CHAT_WINDOW_SECONDS) 안에 쓸 수 있는 채팅의 수
    chat_messages_per_window: int = Field(default=5, ge=1)
    chat_window_seconds: int = Field(default=10, ge=1)

    # 공개 금지(블랙리스트, #392). 한 사람의 시나리오가 운영자에게 이만큼 제재되면 저절로 공개를 막는다.
    # 운영자가 풀면 그 뒤의 제재부터 다시 센다. 자기 시나리오와 남의 시나리오로 플레이하는 것은 막지 않는다
    publishing_ban_threshold: int = Field(default=3, ge=1)

    @model_validator(mode='after')
    def require_a_revocations_url(self) -> Self:
        """끊긴 세션 목록의 주소를 알 수 없으면 뜨지 않는다. 목록 없이 뜨면 끊긴 세션이 만료까지 통한다."""
        if not self.auth_session_revocations_url.strip() and not self.auth_jwks_url.endswith(JWKS_PATH):
            raise ValueError(
                f'AUTH_JWKS_URL 이 {JWKS_PATH} 로 끝나지 않는다. AUTH_SESSION_REVOCATIONS_URL 을 적어야 한다'
            )
        return self

    @property
    def session_revocations_url(self) -> str:
        """끊긴 세션 목록의 주소. 적은 값이 있으면 그것, 없으면 공개키 주소 옆이다."""
        written = self.auth_session_revocations_url.strip()
        return written or self.auth_jwks_url.removesuffix(JWKS_PATH) + SESSION_REVOCATIONS_PATH

    @model_validator(mode='after')
    def require_a_model_for_llm(self) -> Self:
        """언어 모델로 서술하겠다면서 모델 이름이 없으면 뜨지 않는다. 첫 라운드를 닫을 때 알게 되는 것보다 낫다."""
        if self.narrator == 'llm' and not self.llm_model.strip():
            raise ValueError('NARRATOR=llm 이면 LLM_MODEL 을 적어야 합니다')
        return self

    @model_validator(mode='after')
    def require_an_embedding_model(self) -> Self:
        """임베딩 모델로 벡터를 만들겠다면서 모델 이름이 없으면 뜨지 않는다."""
        if self.embedder == 'llm' and not self.embedding_model.strip():
            raise ValueError('EMBEDDER=llm 이면 EMBEDDING_MODEL 을 적어야 합니다')
        return self

    @model_validator(mode='after')
    def require_a_billing_secret(self) -> Self:
        """결제 서버를 부르겠다면서 비밀이 없거나 짧으면 뜨지 않는다. 결제 서버가 모든 요청을 401 로 거절한다."""
        if self.billing_url.strip() and len(self.billing_secret.get_secret_value()) < BILLING_SECRET_MIN_LENGTH:
            raise ValueError(
                f'BILLING_URL 을 적었으면 BILLING_SECRET 을 {BILLING_SECRET_MIN_LENGTH}자 이상 적어야 합니다'
            )
        return self

    @model_validator(mode='after')
    def require_a_long_signal_secret(self) -> Self:
        """신호의 비밀을 적었는데 짧으면 뜨지 않는다. 비운 것은 괜찮다(무작위로 만든다)."""
        secret = self.signal_secret.get_secret_value().strip()
        if secret and len(secret) < SIGNAL_SECRET_MIN_LENGTH:
            raise ValueError(f'SIGNAL_SECRET 은 {SIGNAL_SECRET_MIN_LENGTH}자 이상이어야 합니다')
        return self

    def digest_key(self) -> bytes | None:
        """입력 지문의 키. 비어 있으면 None 이다(지문을 남기지 않는다)."""
        key = self.ai_log_hmac_key.get_secret_value().strip()
        return key.encode() if key else None

    def signal_key(self) -> bytes | None:
        """신호에 서명하는 키. 비어 있으면 None 이다(서버가 뜰 때 무작위로 만든다)."""
        secret = self.signal_secret.get_secret_value().strip()
        return secret.encode() if secret else None

    def embedding_url(self) -> str:
        """임베딩 모델을 부르는 주소. 따로 적지 않았으면 언어 모델과 같은 주소다."""
        return self.embedding_base_url.strip() or self.llm_base_url

    def llm_models(self) -> list[str]:
        """standard 등급으로 부를 모델들을 부를 차례대로. 첫 모델 다음에 넘어갈 모델들이다."""
        return model_chain(self.llm_model, self.llm_fallback_models)

    def draft_model_name(self) -> str:
        """장부 초안을 쓰는 모델. DRAFT_MODEL 을 적지 않았으면 기본 모델(LLM_MODEL)이다."""
        return self.draft_model.strip() or self.llm_models()[0]


@lru_cache
def get_settings() -> Settings:
    """
    설정을 읽어 돌려준다. 처음 한 번만 읽고 그 뒤로는 같은 객체를 돌려준다.

    요청마다 .env 파일을 다시 읽지 않기 위해서다.
    """
    return Settings()
