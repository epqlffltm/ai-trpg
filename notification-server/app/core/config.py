# notification-server/app/core/config.py

"""
알림 서버의 설정. 환경 변수와 notification-server/.env 에서 읽는다.

FastAPI 서버들이 함께 쓰는 칸(DB, 인증 서버, 로그, 수집기)은 공용 코드의 설정(server_core.settings.CoreSettings)에 있다.
여기에는 이 서버의 이름과 기본값, 이 서버만의 칸(알림의 보관, 넣는 서버와 인증 서버의 서명 비밀)을 둔다.

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
    service_name: ClassVar[str] = 'notification-server'

    # 테이블을 두는 스키마. 테스트는 notification_test 로 바꿔서 개발용 데이터와 섞이지 않게 한다
    db_schema: str = Field(default='notification', pattern=SCHEMA_PATTERN)

    # 이 서버의 이름. 토큰의 대상 목록(aud)에 이 이름이 있어야 받는다.
    # 다른 서버용으로 발급된 토큰을 이 서버에 쓰는 것을 막는다
    jwt_audience: str = 'ai-trpg-notification'

    # 알림을 지우기 전까지 두는 날 수. 받은 시각부터 센다(app/notifications/retention.py)
    notification_retention_days: int = Field(default=30, ge=1)

    # 알림을 넣는 서버마다의 서명 비밀(server_core/service_auth/signing.py). 그 서버의 설정에 같은 값을 적는다.
    # 서버마다 따로 둔다. 하나가 새도 그 비밀로 다른 서버인 척 알림을 넣을 수 없다.
    # 비워 두면 그 서버의 알림은 하나도 받지 않는다(401). 적으면 32자 이상이고 서로 달라야 한다
    game_server_secret: SecretStr = SecretStr('')
    billing_server_secret: SecretStr = SecretStr('')
    board_server_secret: SecretStr = SecretStr('')
    # asset 서버(캐릭터의 숨김, 캐릭터 신고의 처리)와 chat 서버(대화 속 답의 신고의 처리)의 것(#678)
    asset_server_secret: SecretStr = SecretStr('')
    chat_server_secret: SecretStr = SecretStr('')
    # story 서버(세션 속 답의 신고의 처리)의 것
    story_server_secret: SecretStr = SecretStr('')

    # 인증 서버가 탈퇴를 알리는 요청의 서명 비밀(#603, app/withdrawals/).
    # 인증 서버의 NOTIFICATION_SECRET 과 같은 값이다.
    # 알림을 넣는 비밀(service_secrets)과 따로 둔다. 인증 서버는 알림을 넣지 않고, 넣는 서버는 탈퇴를 알릴 수 없다.
    # 비워 두면 탈퇴의 알림을 받지 않는다(401). 인증 서버는 비밀을 적은 뒤에 쌓인 것부터 다시 보낸다
    auth_server_secret: SecretStr = SecretStr('')

    @model_validator(mode='after')
    def require_strong_distinct_secrets(self) -> Self:
        """적은 서명 비밀이 짧거나 서로 같으면 뜨지 않는다. 받기 시작한 뒤에 모든 요청이 401 인 것보다 낫다."""
        written = [secret for secret in self.all_secrets() if secret]
        if any(len(secret) < MIN_SECRET_LENGTH for secret in written):
            raise ValueError(f'서명 비밀(*_SERVER_SECRET)은 {MIN_SECRET_LENGTH}자 이상이어야 한다')
        if len(set(written)) != len(written):
            raise ValueError('서명 비밀(*_SERVER_SECRET)은 서버마다 달라야 한다')
        return self

    def service_secrets(self) -> dict[str, str]:
        """알림을 넣는 서버의 이름과 그 서버의 서명 비밀. 비어 있으면 그 서버의 알림을 받지 않는다."""
        return {
            'game': self.game_server_secret.get_secret_value(),
            'billing': self.billing_server_secret.get_secret_value(),
            'board': self.board_server_secret.get_secret_value(),
            'asset': self.asset_server_secret.get_secret_value(),
            'chat': self.chat_server_secret.get_secret_value(),
            'story': self.story_server_secret.get_secret_value(),
        }

    def all_secrets(self) -> list[str]:
        """이 서버가 확인하는 서명 비밀 전부. 알림을 넣는 서버들과 인증 서버의 것이다. 비어 있는 것도 들어 있다."""
        return [*self.service_secrets().values(), self.auth_server_secret.get_secret_value()]


@lru_cache
def get_settings() -> Settings:
    """
    설정을 읽어 돌려준다. 처음 한 번만 읽고 그 뒤로는 같은 객체를 돌려준다.

    요청마다 .env 를 다시 읽지 않는다. 테스트는 이 함수를 거치지 않고 Settings 를 직접 만들어 앱에 넣는다.
    """
    return Settings()
