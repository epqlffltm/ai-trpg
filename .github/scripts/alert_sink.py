# .github/scripts/alert_sink.py

"""
경보를 받는 곳(Discord, Slack, Telegram, 바깥 감시)의 흉내. stack-smoke.sh 의 check 가 observability 망에 띄운다.

Alertmanager 가 보낸 요청을 받아 그 경로를 적어 두고, 받는 곳이 답하는 모양으로 답한다.
GET /received 는 지금까지 받은 경로를 JSON 목록으로 낸다. 본문(경보의 내용)은 적지 않는다.

    사용: python3 alert_sink.py [포트]   (기본 8080)
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Telegram 의 sendMessage 가 성공했을 때의 답. 보낸 메시지를 돌려준다
TELEGRAM_REPLY = {
    'ok': True,
    'result': {'message_id': 1, 'date': 0, 'chat': {'id': 1, 'type': 'private'}, 'text': ''},
}


def reply_for(path: str) -> tuple[int, str, bytes]:
    """그 경로의 받는 곳이 성공했을 때 내는 상태 코드와 형식과 본문."""
    if path.startswith('/telegram/'):
        return 200, 'application/json', json.dumps(TELEGRAM_REPLY).encode()
    if path.startswith('/slack'):
        return 200, 'text/plain', b'ok'
    # Discord 의 웹후크는 본문 없이 204 다
    return 204, 'text/plain', b''


class Sink(BaseHTTPRequestHandler):
    received: list[str] = []

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        self.rfile.read(length)
        self.received.append(self.path)
        self.answer(*reply_for(self.path))

    def do_GET(self):
        if self.path != '/received':
            self.answer(404, 'text/plain', b'')
            return
        self.answer(200, 'application/json', json.dumps(self.received).encode())

    def answer(self, status: int, content_type: str, body: bytes):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # 요청마다의 줄에 Telegram 의 토큰(경로)이 실린다. 찍지 않는다
        pass


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    ThreadingHTTPServer(('0.0.0.0', port), Sink).serve_forever()
    return 0


if __name__ == '__main__':
    sys.exit(main())
