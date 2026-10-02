# auth-server/config/mail_backends.py

"""
개발용 메일 백엔드.

Django 의 console 백엔드는 메일을 실제 전송 형식 그대로 출력한다.
한글 본문은 base64 로 인코딩되어 나와, 터미널에서 인증 코드를 읽을 수 없다.
같은 일을 하되 사람이 읽을 수 있는 형태로 출력한다.
"""

from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend


class ReadableConsoleEmailBackend(ConsoleEmailBackend):
    """메일을 보내지 않고, 받는 사람과 제목과 본문을 터미널에 그대로 출력한다."""

    def write_message(self, message) -> None:
        self.stream.write('-' * 79 + '\n')
        self.stream.write(f'받는 사람: {", ".join(message.to)}\n')
        self.stream.write(f'보내는 사람: {message.from_email}\n')
        self.stream.write(f'제목: {message.subject}\n\n')
        self.stream.write(f'{message.body}\n')
        self.stream.write('-' * 79 + '\n')