# auth-server/config/mail_backends.py

"""
개발용 메일 백엔드.

Django 의 console 백엔드는 메일을 실제 전송 형식 그대로 출력한다.
한글 본문은 base64 로 인코딩되어 나와, 터미널에서 인증 코드를 읽을 수 없다.
같은 일을 하되 사람이 읽을 수 있는 형태로 출력한다.

개발할 때만 쓴다. 출력에 받는 사람의 주소와 인증 코드가 그대로 찍힌다. 운영 환경에서는 쓸 수 없게 막는다
(require_real_mailer_in_production). staging 은 운영자 혼자 쓰는 서버라 허용한다(config/environments.py).
"""

from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend

from config.environments import is_deployed, is_production


def require_real_mailer_in_production(smtp_host: str, environment: str) -> None:
    """
    운영 환경인데 메일 서버가 정해져 있지 않으면 서버가 뜨지 않게 한다. 설정을 읽을 때 부른다(config/settings.py).

    메일 서버가 없으면 메일을 보내지 않고 터미널에 출력한다(아래의 ReadableConsoleEmailBackend).
    그 출력에는 받는 사람의 주소와 인증 코드, 비밀번호 재설정 링크가 그대로 찍힌다. 운영에서는 표준 출력이
    로그와 함께 모인다. 그대로 두면 인증 코드가 로그에 남는다(저장소 루트의 docs/observability.md).
    """
    if not smtp_host and is_production(environment):
        raise ImproperlyConfigured('운영 환경(APP_ENVIRONMENT=production)에서는 SMTP_HOST 를 적어야 합니다.')


def forbid_debug_when_deployed(debug: bool, environment: str) -> None:
    """
    바깥에 연 환경(staging, production)인데 DEBUG 가 켜져 있으면 서버가 뜨지 않게 한다.
    설정을 읽을 때 부른다(config/settings.py).

    DEBUG 가 켜져 있으면 Django 는 처리하지 못한 예외의 응답에 호출 기록과 설정값을 실어 보낸다.
    개발할 때는 편하지만, 바깥에 연 서버에서는 내부의 구조가 밖으로 나간다(저장소 루트의 docs/observability.md).
    staging 도 막는다. .env.example 을 그대로 옮기면 DEBUG=true 라서, 막지 않으면 틀린 채로 뜬다.
    """
    if debug and is_deployed(environment):
        raise ImproperlyConfigured(
            f'바깥에 연 환경(APP_ENVIRONMENT={environment})에서는 DEBUG 를 켤 수 없습니다. DEBUG=false 로 적습니다.'
        )


class ReadableConsoleEmailBackend(ConsoleEmailBackend):
    """메일을 보내지 않고, 받는 사람과 제목과 본문을 터미널에 그대로 출력한다."""

    def write_message(self, message) -> None:
        self.stream.write('-' * 79 + '\n')
        self.stream.write(f'받는 사람: {", ".join(message.to)}\n')
        self.stream.write(f'보내는 사람: {message.from_email}\n')
        self.stream.write(f'제목: {message.subject}\n\n')
        self.stream.write(f'{message.body}\n')
        self.stream.write('-' * 79 + '\n')
