# shared/server-core/src/server_core/settings.py

"""
FastAPI 서버들이 함께 쓰는 설정의 칸. 서버의 설정(app/core/config.py)이 이것을 물려받아 제 칸을 더한다.

공용 코드는 설정 파일을 읽지 않는다. 서버가 읽어 만든 설정을 받아 쓴다
(docs/architecture/shared-code.md 의 "재정의하는 법").
물려받는 것은 설정뿐이다. 서버마다 다른 값은 셋이다(연결 풀의 크기처럼 환경마다 다른 값은 환경 변수로 준다).

  - service_name: 이 서버의 이름(asset-server). 로그의 service 칸, span 과 메트릭의 출처가 된다. 클래스에 적는다.
    환경 변수로 바꿀 수 없다. 이름이 바뀌면 대시보드와 경보가 그 서버를 잃는다
  - db_schema 와 jwt_audience 의 기본값. 서버가 같은 이름의 칸을 다시 적어 기본값을 준다

    class Settings(CoreSettings):
        service_name: ClassVar[str] = 'asset-server'
        db_schema: str = Field(default='asset', pattern=SCHEMA_PATTERN)
        jwt_audience: str = 'ai-trpg-asset'

비밀값과 환경마다 달라지는 값은 코드에 적지 않는다. 서버마다 .env 를 따로 둔다.
한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.
"""

from typing import ClassVar, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 인증 서버의 두 주소의 끝. 둘은 같은 곳(/api/v1/auth)에 있다
JWKS_PATH = '/jwks'
SESSION_REVOCATIONS_PATH = '/session-revocations'
# 수집기의 주소로 받는 앞부분
OTLP_SCHEMES = ('http', 'https')
# 스키마 이름의 모양. 소문자로 시작하고 소문자, 숫자, 밑줄로 63자까지(PostgreSQL 의 이름 길이)
SCHEMA_PATTERN = r'^[a-z][a-z0-9_]{0,62}$'


def otlp_endpoint(value: str) -> str:
    """
    수집기의 주소를 읽는다. 비어 있으면 빈 글자다. 있으면 http:// 나 https:// 로 시작하고 경로가 없어야 한다.

    경로(/v1/traces)는 보내는 쪽이 붙인다. OpenTelemetry 의 OTEL_EXPORTER_OTLP_ENDPOINT 와 같은 뜻이고,
    결제 서버의 같은 설정과 같은 규칙이다. 끝의 / 는 뗀다.
    """
    written = value.strip()
    if not written:
        return ''
    parts = urlsplit(written)
    if parts.scheme not in OTLP_SCHEMES or not parts.netloc:
        raise ValueError('OTEL_EXPORTER_OTLP_ENDPOINT 는 http:// 나 https:// 로 시작해야 한다')
    if parts.path.strip('/') or parts.query or parts.fragment:
        raise ValueError(
            'OTEL_EXPORTER_OTLP_ENDPOINT 는 http://alloy:4318 처럼 경로 없이 적는다. /v1/traces 는 붙이지 않는다'
        )
    return written.rstrip('/')


class CoreSettings(BaseSettings):
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

    # 이 서버의 이름. 서버의 설정이 클래스에 적는다. 규격(docs/observability.md)에 적힌 이름이다
    service_name: ClassVar[str] = 'server'

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
    # 엉뚱한 DB 를 기본으로 쓰는 것보다 뜨지 않는 쪽이 낫다.
    # 예: postgresql+asyncpg://asset:비밀번호@127.0.0.1:5432/trpg
    database_url: str

    # 테이블을 두는 스키마. 서버의 설정이 기본값(서버의 이름)을 준다.
    # 테스트는 <이름>_test 로 바꿔서 개발용 데이터와 섞이지 않게 한다
    db_schema: str = Field(pattern=SCHEMA_PATTERN)

    # 연결 풀이 늘 들고 있는 연결과, 붐빌 때 더 맺는 연결. 둘의 합(db_max_connections)이
    # 이 서버가 DB 에 쥘 수 있는 가장 많은 연결이다. 모든 서버의 합이 DB 의 max_connections 안에 들어야 한다.
    # 서버마다의 값은 compose 가 준다(docs/architecture/services.md 의 "DB 와 Redis 의 한도", #592).
    # 기본은 SQLAlchemy 의 기본값이다
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=10, ge=0, le=50)

    # 인증 서버가 공개키를 내주는 주소(JWKS). 기본값이 없다.
    # 여기서 받은 키로 서명된 토큰을 믿는다. 엉뚱한 주소를 기본으로 믿는 것보다 뜨지 않는 쪽이 낫다.
    # 예: http://127.0.0.1:8000/api/v1/auth/jwks
    auth_jwks_url: str

    # 인증 서버가 끊긴 세션의 목록을 내주는 주소(#274). 비우면 AUTH_JWKS_URL 옆(…/session-revocations)이다.
    # AUTH_JWKS_URL 이 /jwks 로 끝나지 않으면 적어야 한다. 쓰는 곳은 session_revocations_url 이다
    auth_session_revocations_url: str = ''

    # 토큰을 발급한 서버의 이름(iss). 인증 서버의 JWT_ISSUER 와 같아야 한다
    jwt_issuer: str = 'ai-trpg-auth'

    # 이 서버의 이름. 토큰의 대상 목록(aud)에 이 이름이 있어야 받는다. 서버의 설정이 기본값을 준다.
    # 다른 서버용으로 발급된 토큰을 이 서버에 쓰는 것을 막는다
    jwt_audience: str

    # span 과 메트릭을 OTLP(HTTP)로 미는 수집기(Alloy)의 주소. 경로 없이 적는다(http://alloy:4318).
    # 비우면 내보내지 않는다. 로그는 그대로다(server_core/observability/tracing.py, metrics.py)
    otel_exporter_otlp_endpoint: str = ''

    # 메트릭을 보내는 간격(밀리초). 결제 서버와 같은 이름과 기본값이다.
    # SDK 의 기본(60초)이면 rate(…[1m]) 에 점이 하나뿐이다
    otel_metric_export_interval: int = Field(default=15000, ge=1000)

    @field_validator('otel_exporter_otlp_endpoint')
    @classmethod
    def check_otlp_endpoint(cls, value: str) -> str:
        """수집기의 주소가 틀렸으면 뜨지 않는다. 틀린 주소로 보내며 경고를 쌓는 것보다 낫다."""
        return otlp_endpoint(value)

    @model_validator(mode='after')
    def require_a_revocations_url(self) -> Self:
        """끊긴 세션 목록의 주소를 알 수 없으면 뜨지 않는다. 목록 없이 뜨면 끊긴 세션이 만료까지 통한다."""
        if not self.auth_session_revocations_url.strip() and not self.auth_jwks_url.endswith(JWKS_PATH):
            raise ValueError(
                f'AUTH_JWKS_URL 이 {JWKS_PATH} 로 끝나지 않는다. AUTH_SESSION_REVOCATIONS_URL 을 적어야 한다'
            )
        return self

    @property
    def db_max_connections(self) -> int:
        """이 서버의 풀이 DB 에 쥘 수 있는 가장 많은 연결. 메트릭 db_pool_connections_max 의 값이다."""
        return self.db_pool_size + self.db_max_overflow

    @property
    def session_revocations_url(self) -> str:
        """끊긴 세션 목록의 주소. 적은 값이 있으면 그것, 없으면 공개키 주소 옆이다."""
        written = self.auth_session_revocations_url.strip()
        return written or self.auth_jwks_url.removesuffix(JWKS_PATH) + SESSION_REVOCATIONS_PATH
