# game-server/app/core/config.py

"""
게임 서버의 설정. 환경 변수와 game-server/.env 에서 읽는다.

비밀값과 환경마다 달라지는 값은 코드에 적지 않는다.
인증 서버의 .env 와 따로 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 서술 하나에 쓰는 시간의 상한(초). 다시 시도하기와 다음 모델로 넘어가기를 모두 이 안에서 한다
# (app/rounds/retrying_narrator.py).
# 한 번 부르는 시간(LLM_TIMEOUT_SECONDS)은 이보다 길 수 없다. 길면 첫 시도만으로 상한을 넘는다
NARRATION_BUDGET_SECONDS = 150.0


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

    # 모델의 이름. narrator=llm 이면 반드시 적는다(예: gemma4:26b)
    llm_model: str = ''

    # 첫 모델이 끝내 실패하면 차례로 넘어갈 모델들. 쉼표로 나눠 적는다(예: gemma4:31b-it-qat,qwen3.6:27b).
    # 비우면 넘어가지 않는다(기본). 같은 주소(LLM_BASE_URL)의 모델들이다
    llm_fallback_models: str = ''

    # 모델의 답을 한 번 기다리는 시간(초). 처음 부를 때는 모델을 메모리에 올리느라 수십 초가 걸린다.
    # 서술은 요청과 따로 도는 작업이라 플레이어의 요청이 이만큼 기다리지는 않는다.
    # 서술 하나의 상한(NARRATION_BUDGET_SECONDS)보다 길 수 없다
    llm_timeout_seconds: float = Field(default=60.0, gt=0, le=NARRATION_BUDGET_SECONDS)

    # 모델이 추론 수준(reasoning_effort)을 아는가. 알면 늘 보내서 기본으로 추론을 끈다.
    # 모르는 모델에 보냈다가 오류가 나면 false 로 바꾼다
    llm_supports_reasoning: bool = True

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

    def embedding_url(self) -> str:
        """임베딩 모델을 부르는 주소. 따로 적지 않았으면 언어 모델과 같은 주소다."""
        return self.embedding_base_url.strip() or self.llm_base_url

    def llm_models(self) -> list[str]:
        """부를 모델들을 부를 차례대로. 첫 모델 다음에 넘어갈 모델들이다. 빈 이름과 앞뒤 공백은 뺀다."""
        fallbacks = [name.strip() for name in self.llm_fallback_models.split(',')]
        return [self.llm_model.strip(), *(name for name in fallbacks if name)]


@lru_cache
def get_settings() -> Settings:
    """
    설정을 읽어 돌려준다. 처음 한 번만 읽고 그 뒤로는 같은 객체를 돌려준다.

    요청마다 .env 파일을 다시 읽지 않기 위해서다.
    """
    return Settings()
