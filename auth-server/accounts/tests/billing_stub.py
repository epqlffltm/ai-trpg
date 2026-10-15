# auth-server/accounts/tests/billing_stub.py

"""
테스트가 쓰는 가짜 결제 서버.

이 PC 의 빈 포트에 진짜 HTTP 서버를 띄운다. 요청을 보내는 함수를 가짜로 바꿔 끼우지 않고
실제로 보내게 해서, 나가는 바이트(주소, 머리말, 본문, 서명)를 그대로 받아 본다.
정해 둔 대로 답하고, 받은 요청을 적어 둔다.
"""

import contextlib
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from accounts.service_signature import SIGNATURE_HEADER, sign_request

# 테스트의 인증 서버와 가짜 결제 서버가 함께 아는 비밀
SECRET = 'auth-server-test-secret-of-32-chars'


@dataclass
class ReceivedRequest:
    """가짜 결제 서버가 받은 요청 하나."""

    method: str
    path: str
    headers: dict[str, str]
    body: bytes

    def has_valid_signature(self, secret: str = SECRET) -> bool:
        """결제 서버가 하듯, 받은 바이트로 서명을 다시 만들어 머리말의 것과 견준다."""
        header = self.headers.get(SIGNATURE_HEADER, '')
        sent_at = header.partition(',')[0].removeprefix('t=')
        if not sent_at.isdigit():
            return False
        expected = sign_request(
            secret=secret,
            method=self.method,
            request_uri=self.path,
            body=self.body,
            sent_at=int(sent_at),
        )
        return header == expected


@dataclass
class BillingStub:
    """
    가짜 결제 서버. with 로 띄우고, 블록을 나가면 꺼진다.

    status_code 와 body 는 모든 요청에 돌려줄 답이다. headers 는 답에 더 붙일 머리말이다.
    delay_seconds 를 주면 답하기 전에 그만큼 기다린다.
    """

    status_code: int = 201
    body: bytes = b'{"status":"granted","granted":"1000","expires_at":"2026-03-09T09:00:00Z"}'
    headers: dict[str, str] = field(default_factory=dict)
    delay_seconds: float = 0
    requests: list[ReceivedRequest] = field(default_factory=list)

    def __enter__(self) -> 'BillingStub':
        self._release = threading.Event()
        self._server = ThreadingHTTPServer(('127.0.0.1', 0), self._handler())
        # 꺼 달라는 말을 자주 확인하게 한다. 기본값(0.5초)이면 서버를 끌 때마다 그만큼 기다린다
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc_info) -> None:
        # 기다리게 해 둔 답이 있으면 풀어 준다. 그래야 서버가 꺼진다
        self._release.set()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @property
    def url(self) -> str:
        host, port = self._server.server_address
        return f'http://{host}:{port}'

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                self._answer()

            def do_GET(self) -> None:
                self._answer()

            def _answer(self) -> None:
                length = int(self.headers.get('Content-Length') or 0)
                stub.requests.append(
                    ReceivedRequest(
                        method=self.command,
                        path=self.path,
                        headers=dict(self.headers.items()),
                        body=self.rfile.read(length),
                    )
                )
                if stub.delay_seconds:
                    stub._release.wait(stub.delay_seconds)
                # 쓰다가 OSError 가 나면 기다리다 지친 쪽이 먼저 연결을 끊은 것이다.
                # 시간 초과를 보는 테스트에서 일부러 만드는 상황이다
                with contextlib.suppress(OSError):
                    self._write_answer()

            def _write_answer(self) -> None:
                self.send_response(stub.status_code)
                for name, value in stub.headers.items():
                    self.send_header(name, value)
                self.send_header('Content-Length', str(len(stub.body)))
                self.end_headers()
                self.wfile.write(stub.body)

            def log_message(self, *args) -> None:
                # 테스트의 출력에 요청 기록을 찍지 않는다
                pass

        return Handler


def closed_port_url() -> str:
    """아무도 듣고 있지 않은 주소. 서버를 띄웠다가 바로 꺼서 얻는다."""
    with BillingStub() as stub:
        url = stub.url
    return url
