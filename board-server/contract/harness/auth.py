# board-server/contract/harness/auth.py

"""
인증 서버를 흉내 내는 작은 HTTP 서버. 게시판 서버가 부르는 두 주소만 답한다.

  - GET /api/v1/auth/jwks: 공개키 목록. 시험이 키를 바꿔 끼울 수 있다(키를 바꾼 인증 서버)
  - GET /api/v1/auth/session-revocations: 끊긴 세션의 목록. 늘 비어 있다

몇 번 불렸는지 센다. 공개키를 요청마다 묻지 않고 기억해 쓰는지 본다.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

JWKS_PATH = '/api/v1/auth/jwks'
REVOCATIONS_PATH = '/api/v1/auth/session-revocations'
# 인증 서버가 정한 다시 받는 간격(초). 게시판 서버와 같다
REVOCATIONS_INTERVAL_SECONDS = 30


class FakeAuthServer:
    """공개키 목록을 내주는 가짜 인증 서버. start 로 띄우고 stop 으로 닫는다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._keys: list[dict[str, Any]] = []
        self._calls: dict[str, int] = {}
        self._failing = False
        self._server: ThreadingHTTPServer | None = None

    @property
    def jwks_url(self) -> str:
        return f'{self._base_url()}{JWKS_PATH}'

    def _base_url(self) -> str:
        if self._server is None:
            raise RuntimeError('가짜 인증 서버를 먼저 띄운다')
        host, port = self._server.server_address[:2]
        return f'http://{host}:{port}'

    def set_keys(self, *jwks: dict[str, Any]) -> None:
        """공개키 목록을 바꾼다."""
        with self._lock:
            self._keys = list(jwks)

    def set_failing(self, failing: bool) -> None:
        """참이면 공개키 목록을 500 으로 답한다(죽은 인증 서버)."""
        with self._lock:
            self._failing = failing

    def calls(self, path: str = JWKS_PATH) -> int:
        """그 주소가 몇 번 불렸는가."""
        with self._lock:
            return self._calls.get(path, 0)

    def respond(self, path: str) -> tuple[int, dict[str, Any] | None]:
        """주소에 맞는 답. 모르는 주소는 404."""
        with self._lock:
            self._calls[path] = self._calls.get(path, 0) + 1
            if path == JWKS_PATH:
                return (500, None) if self._failing else (200, {'keys': list(self._keys)})
            if path == REVOCATIONS_PATH:
                return 200, {'revocations': [], 'refresh_interval_seconds': REVOCATIONS_INTERVAL_SECONDS}
            return 404, None

    def start(self) -> None:
        """127.0.0.1 의 빈 포트에서 띄운다."""
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server 가 정한 이름이다
                status, body = owner.respond(self.path.split('?', 1)[0])
                payload = b'' if body is None else json.dumps(body).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - 부모의 이름 그대로
                return

        self._server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
