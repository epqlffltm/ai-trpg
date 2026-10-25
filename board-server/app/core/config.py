# board-server/app/core/config.py

"""
게시판 서버의 설정. 환경 변수와 board-server/.env 에서 읽는다.

FastAPI 서버들이 함께 쓰는 칸(DB, 인증 서버, 로그, 수집기)은 공용 코드의 설정(server_core.settings.CoreSettings)에 있다.
여기에는 이 서버의 이름과 기본값, 이 서버만의 칸(띄우는 주소와 포트, 탈퇴를 알리는 인증 서버의 서명 비밀)을 둔다.

환경 변수의 이름은 NestJS 로 쓰던 때와 같다(#785). compose 와 계약 시험(contract/)이 같은 이름으로 넘긴다.
  - DATABASE_URL 은 postgresql:// 로 적어도 된다. 비동기 드라이버(asyncpg)의 주소로 바꿔 쓴다
  - HOST, PORT 는 서버를 띄우는 곳이다(python -m app). 다른 서버처럼 uvicorn 의 인자로 넘기지 않는다

비밀값과 환경마다 달라지는 값은 코드에 적지 않는다. 다른 서버의 .env 와 따로 둔다.
"""

from functools import lru_cache
from typing import ClassVar, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from server_core.notifications.settings import NotificationSettings
from server_core.service_auth.signing import MIN_SECRET_LENGTH
from server_core.settings import SCHEMA_PATTERN, CoreSettings

# 동기 드라이버의 주소 앞부분과 이 서버가 쓰는 비동기 드라이버의 주소 앞부분
PLAIN_SCHEMES = ('postgresql://', 'postgres://')
ASYNC_SCHEME = 'postgresql+asyncpg://'


def async_database_url(value: str) -> str:
    """postgresql:// 로 적은 주소를 asyncpg 의 주소로 바꾼다. 이미 바꾼 주소는 그대로다."""
    for scheme in PLAIN_SCHEMES:
        if value.startswith(scheme):
            return ASYNC_SCHEME + value.removeprefix(scheme)
    return value


class Settings(CoreSettings, NotificationSettings):
    """
    설정 값의 목록과 형식. 함께 쓰는 칸은 CoreSettings 에, 알림 서버의 칸(NOTIFICATION_URL, NOTIFICATION_SECRET,
    NOTIFICATION_TIMEOUT_SECONDS)은 NotificationSettings 에 있다.

    같은 이름의 환경 변수가 있으면 그 값을 쓰고, 없으면 .env 파일, 그것도 없으면 여기 적힌 기본값을 쓴다.
    형식이 맞지 않으면 서버가 뜨기 전에 오류가 난다.
    """

    # 이 서버의 이름. 로그의 service 칸, span 과 메트릭의 출처다. 규격(docs/observability.md)에 적힌 이름이다
    service_name: ClassVar[str] = 'board-server'

    # 테이블을 두는 스키마. 테스트는 board_test 로 바꿔서 개발용 데이터와 섞이지 않게 한다
    db_schema: str = Field(default='board', pattern=SCHEMA_PATTERN)

    # DB 연결의 풀. 풀 5 + 넘침 5 = 10 이 이 서버의 몫이다(docs/architecture/services.md 의 "DB 와 Redis 의 한도").
    # 공용 코드의 기본값(5 + 10)을 따르면 몫을 넘는다
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)

    # 이 서버의 이름. 토큰의 대상 목록(aud)에 이 이름이 있어야 받는다
    jwt_audience: str = 'ai-trpg-board'

    # 서버를 띄우는 주소와 포트(app/__main__.py). 기본은 이 PC 안에서만 닿는 주소다. compose 는 0.0.0.0 을 넘긴다
    host: str = '127.0.0.1'
    port: int = Field(default=8002, ge=1, le=65535)

    # 인증 서버가 탈퇴를 알리는 요청(app/withdrawal/)의 서명 비밀. 인증 서버의 BOARD_SECRET 과 같은 값이다.
    # 비워 두면 탈퇴 알림을 받지 않는다(401). 인증 서버는 받을 때까지 다시 보낸다
    auth_server_secret: SecretStr = SecretStr('')

    @field_validator('database_url')
    @classmethod
    def use_async_driver(cls, value: str) -> str:
        return async_database_url(value)

    @model_validator(mode='after')
    def require_a_strong_secret(self) -> Self:
        """적은 서명 비밀이 짧으면 뜨지 않는다. 받기 시작한 뒤에 모든 알림이 401 인 것보다 낫다."""
        secret = self.auth_server_secret.get_secret_value()
        if secret and len(secret) < MIN_SECRET_LENGTH:
            raise ValueError(f'AUTH_SERVER_SECRET 은 {MIN_SECRET_LENGTH}자 이상이어야 한다')
        return self


@lru_cache
def get_settings() -> Settings:
    """
    설정을 읽어 돌려준다. 처음 한 번만 읽고 그 뒤로는 같은 객체를 돌려준다.

    요청마다 .env 를 다시 읽지 않는다. 테스트는 이 함수를 거치지 않고 Settings 를 직접 만들어 앱에 넣는다.
    """
    return Settings()
