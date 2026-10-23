# shared/server-core/src/server_core/notifications/settings.py

"""
알림을 보내는 서버의 설정 칸. 서버의 설정이 CoreSettings 와 함께 물려받는다.

    class Settings(CoreSettings, NotificationSettings):
        ...

주소를 비우면 알림은 발송함에 적히기만 하고 보내지 않는다(테스트, 알림 서버 없는 개발).
주소를 적었는데 비밀이 짧으면 뜨지 않는다. 뜬 뒤에 모든 알림이 401 로 쌓이는 것보다 낫다.
"""

from typing import Self

from pydantic import BaseModel, Field, SecretStr, model_validator

from server_core.service_auth.signing import MIN_SECRET_LENGTH


class NotificationSettings(BaseModel):
    """알림 서버의 주소, 서명 비밀, 시간 상한."""

    # 알림 서버의 주소. 예: http://notification-server:8004. 비우면 보내지 않고 발송함에 적기만 한다
    notification_url: str = ''

    # 알림 서버에 넣을 때 서명하는 비밀. 알림 서버의 <이 서버>_SERVER_SECRET 과 같은 값이다(32자 이상)
    notification_secret: SecretStr = SecretStr('')

    # 알림 서버를 부를 때 기다리는 최대 시간(초). 넘기면 다시 보낼 일이다
    notification_timeout_seconds: float = Field(default=5.0, gt=0, le=30)

    @model_validator(mode='after')
    def require_a_notification_secret(self) -> Self:
        """주소를 적었으면 비밀도 길게 적어야 한다."""
        secret = self.notification_secret.get_secret_value()
        if self.notification_url.strip() and len(secret) < MIN_SECRET_LENGTH:
            raise ValueError(
                f'NOTIFICATION_URL 을 적었으면 NOTIFICATION_SECRET 을 {MIN_SECRET_LENGTH}자 이상 적어야 합니다'
            )
        return self
