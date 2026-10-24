# asset-server/app/core/config.py

"""
asset 서버의 설정. 환경 변수와 asset-server/.env 에서 읽는다.

FastAPI 서버들이 함께 쓰는 칸(DB, 인증 서버, 로그, 수집기)은 공용 코드의 설정(server_core.settings.CoreSettings)에 있다.
여기에는 이 서버의 이름과 기본값, 이 서버만의 칸(페르소나의 상한, 캐릭터를 만드는 사람,
부르는 서버와 인증 서버의 서명 비밀, 그림 저장소와 그림을 여는 상한)을 둔다.

비밀값과 환경마다 달라지는 값은 코드에 적지 않는다.
다른 서버의 .env 와 따로 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.
"""

from functools import lru_cache
from typing import ClassVar, Self

from pydantic import Field, SecretStr, model_validator
from server_core.notifications.settings import NotificationSettings
from server_core.service_auth.signing import MIN_SECRET_LENGTH
from server_core.settings import SCHEMA_PATTERN, CoreSettings


class Settings(CoreSettings, NotificationSettings):
    """
    설정 값의 목록과 형식. 함께 쓰는 칸은 CoreSettings 에 있다.
    알림 서버의 칸(NOTIFICATION_URL, NOTIFICATION_SECRET, NOTIFICATION_TIMEOUT_SECONDS)은
    NotificationSettings 에 있다(#678).

    같은 이름의 환경 변수가 있으면 그 값을 쓰고, 없으면 .env 파일, 그것도 없으면 여기 적힌 기본값을 쓴다.
    형식이 맞지 않으면(예: DEBUG=maybe) 서버가 뜨기 전에 오류가 난다.
    """

    # 이 서버의 이름. 로그의 service 칸, span 과 메트릭의 출처다. 규격(docs/observability.md)에 적힌 이름이다
    service_name: ClassVar[str] = 'asset-server'

    # 테이블을 두는 스키마. 테스트는 asset_test 로 바꿔서 개발용 데이터와 섞이지 않게 한다
    db_schema: str = Field(default='asset', pattern=SCHEMA_PATTERN)

    # 이 서버의 이름. 토큰의 대상 목록(aud)에 이 이름이 있어야 받는다.
    # 다른 서버용으로 발급된 토큰을 이 서버에 쓰는 것을 막는다
    jwt_audience: str = 'ai-trpg-asset'

    # 한 사람이 가질 수 있는 계정 페르소나의 수(#565). TRPG 의 보관함과 같은 50 이 기본이다
    persona_max_per_owner: int = Field(default=50, ge=1, le=500)

    # 캐릭터를 누구나 만들 수 있는가(#567). 1~2단계에는 운영자만 만든다(거짓).
    # 3단계에서 일반 사용자에게 열 때 참으로 둔다.
    # 참이어도 공개로 두는 것은 운영자만이다(PUBLIC_FOR_EVERYONE 이 따로 연다)
    characters_for_everyone: bool = False
    # 일반 사용자도 캐릭터를 공개로 둔다(#678). 신고와 운영자의 숨김이 생겨 열 수 있게 되었다.
    # 운영 준비(관리자 화면 E4, 약관)가 되면 켠다. 거짓이면 공개로 두는 것은 운영자만이다
    public_for_everyone: bool = False

    # 페르소나와 판을 가져가는 서버마다의 서명 비밀(server_core/service_auth/signing.py, app/core/service_auth.py).
    # 그 서버의 설정에 같은 값을 적는다(chat 과 story 는 ASSET_SECRET). 서버마다 따로 둔다.
    # 하나가 새도 다른 서버인 척 부를 수 없다. 비워 두면 그 서버의 요청은 하나도 받지 않는다(401). 적으면 32자 이상이다.
    # TRPG 는 그 서버가 가져가기 시작할 때 더한다
    chat_server_secret: SecretStr = SecretStr('')
    # story 서버가 세션을 시작할 때 세계관의 판을 가져간다(app/worlds/supply.py)
    story_server_secret: SecretStr = SecretStr('')

    # 인증 서버가 탈퇴를 알리는 요청(app/withdrawal/)의 서명 비밀. 인증 서버의 ASSET_SECRET 과 같은 값이다.
    # 부르는 서버의 표(service_secrets)에 넣지 않는다. 인증 서버는 페르소나와 판을 가져가는 서버가 아니다.
    # 비워 두면 탈퇴 알림을 받지 않는다(401). 인증 서버는 받을 때까지 다시 보낸다
    auth_server_secret: SecretStr = SecretStr('')

    # 그림 저장소(#566, app/images/store.py). compose 가 넘긴다(docker-compose.yml 의 x-asset-image-store).
    # 주소가 비어 있으면 저장소가 없는 서버다. 그림 올리기와 내주기가 503 이다. 주소를 적으면 나머지도 적어야 뜬다.
    # 주소는 nginx 가 서명한 주소를 따라가는 곳이기도 하다. compose 밖에서 띄우면 nginx 가 그 주소를 받지 않는다
    image_store_endpoint: str = ''
    image_store_region: str = 'ap-northeast-2'
    image_store_bucket: str = ''
    image_store_access_key_id: str = ''
    image_store_secret_access_key: SecretStr = SecretStr('')
    # 저장소에 넣는 요청의 시간 상한(초)
    image_store_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    # 올리는 그림의 크기 상한(바이트). 프록시의 상한(client_max_body_size)이 이보다 조금 크다
    image_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    # 그림을 여는 따로 된 프로세스의 상한(app/images/isolation.py). 픽셀 수(가로 × 세로), 주소 공간(MB),
    # CPU 시간과 벽시계(초), 한꺼번에 여는 수. 메모리는 상한 × 한꺼번에 여는 수까지 쓴다
    image_max_pixels: int = Field(default=40_000_000, ge=1_000_000, le=200_000_000)
    image_decode_memory_mb: int = Field(default=768, ge=128, le=4096)
    image_decode_cpu_seconds: int = Field(default=10, ge=1, le=120)
    image_decode_wall_seconds: float = Field(default=15.0, gt=0, le=180)
    image_decode_concurrency: int = Field(default=2, ge=1, le=16)

    @model_validator(mode='after')
    def require_complete_image_store(self) -> Self:
        """저장소의 주소를 적었으면 버킷과 키도 적어야 한다. 올리기마다 실패하는 것보다 뜨지 않는 것이 낫다."""
        if not self.image_store_endpoint:
            return self
        missing = [
            name
            for name, value in (
                ('IMAGE_STORE_BUCKET', self.image_store_bucket),
                ('IMAGE_STORE_ACCESS_KEY_ID', self.image_store_access_key_id),
                ('IMAGE_STORE_SECRET_ACCESS_KEY', self.image_store_secret_access_key.get_secret_value()),
            )
            if not value
        ]
        if missing:
            raise ValueError(f'IMAGE_STORE_ENDPOINT 를 적었으면 {", ".join(missing)} 도 적어야 한다')
        return self

    @model_validator(mode='after')
    def require_strong_distinct_secrets(self) -> Self:
        """적은 서명 비밀이 짧거나 서로 같으면 뜨지 않는다. 받기 시작한 뒤에 모든 요청이 401 인 것보다 낫다."""
        written = [secret for secret in self.all_secrets() if secret]
        if any(len(secret) < MIN_SECRET_LENGTH for secret in written):
            raise ValueError(f'서명 비밀(*_SERVER_SECRET)은 {MIN_SECRET_LENGTH}자 이상이어야 한다')
        if len(set(written)) != len(written):
            raise ValueError('서명 비밀(*_SERVER_SECRET)은 서버마다 달라야 한다')
        return self

    def all_secrets(self) -> list[str]:
        """이 서버가 받는 모든 서명 비밀. 비어 있는 것도 든다."""
        return [*self.service_secrets().values(), self.auth_server_secret.get_secret_value()]

    def service_secrets(self) -> dict[str, str]:
        """부르는 서버의 이름과 그 서버의 서명 비밀. 비어 있으면 그 서버의 요청을 받지 않는다."""
        return {
            'chat': self.chat_server_secret.get_secret_value(),
            'story': self.story_server_secret.get_secret_value(),
        }


@lru_cache
def get_settings() -> Settings:
    """
    설정을 읽어 돌려준다. 처음 한 번만 읽고 그 뒤로는 같은 객체를 돌려준다.

    요청마다 .env 를 다시 읽지 않는다. 테스트는 이 함수를 거치지 않고 Settings 를 직접 만들어 앱에 넣는다.
    """
    return Settings()
