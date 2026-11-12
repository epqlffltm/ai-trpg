# tools/e2e/stub_llm.py

"""
종단간 테스트(web/e2e)가 쓰는 가짜 언어 모델. OpenAI 호환 주소(/v1/chat/completions) 하나를 흉내 낸다.
표준 라이브러리만 쓴다.

서버들은 이것을 "서버 곁의 모델(local 창구)"로 부른다. 실제 모델과 같은 길을 지난다.
모델 목록과 창구 고르기, 흘려 받기(SSE), 미리 보기, 토큰 수, AI 호출 기록. 게임 서버의 가짜 서술자(FakeNarrator)는
이 길을 하나도 지나지 않아서 종단간 테스트에는 쓰지 않는다.

답은 요청의 모델 이름(api_model_id)으로 고른다(REPLIES). 이름은 e2e 의 모델 목록 파일(local-models.toml)이 정한다.
모르는 이름이면 기본 답이다. 흘려 보낼 때는 답을 조각으로 나눠 조각 사이를 쉰다(STUB_LLM_DELAY 초, 기본 0.2).
서버가 미리 보기를 여러 번 내는지 화면이 볼 수 있다. 맨 끝에 토큰 수(usage)와 [DONE] 을 보낸다.

    사용: python3 tools/e2e/stub_llm.py [--host 0.0.0.0] [--port 11434]

    GET  /health                 살아 있으면 200 "ok"
    POST /v1/chat/completions    stream 이면 SSE, 아니면 JSON 하나
    GET  /v1/requests            받은 요청의 모델 이름들(가장 최근 50개). 테스트가 "정말 불렀는가"를 본다
"""

import argparse
import contextlib
import json
import os
import sys
import threading
import time
from collections import deque
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 모델 이름마다의 답. 테스트가 화면에서 이 글을 찾는다(web/e2e 의 STUB_REPLIES 와 같다)
NARRATION = (
    '등잔불이 흔들리고 수도원의 돌벽 사이로 찬 바람이 스민다. '
    '일행의 발소리가 회랑에 길게 울리고, 멀리서 종이 한 번 운다. '
    '[e2e] 서술이 끝까지 왔다.'
)
# chat 의 답. 캐릭터 한 사람의 말이다
CHAT_REPLY = '[e2e] 세라가 조용히 웃는다. 비가 그칠 때까지 여기 있어도 돼.'
# story 의 답. 줄마다 말하는 사람의 표식이다(story-server 의 app/turns/segments.py). sera 는 견본 세계관의 인물이다
STORY_REPLY = '@narration: [e2e] 학교의 종이 길게 울린다.\n@sera: [e2e] 늦었네. 기다렸어.'
REPLIES = {
    'e2e-narrator': NARRATION,
    'e2e-chat': CHAT_REPLY,
    'e2e-story': STORY_REPLY,
}
DEFAULT_REPLY = '[e2e] 가짜 모델의 답이다.'
# 답을 나누는 조각의 글자 수와, 조각 사이를 쉬는 시간(초)
PIECE_SIZE = 12
DEFAULT_DELAY = 0.2
# 받은 요청을 기억하는 수
REMEMBERED = 50


def reply_for(model: str) -> str:
    """그 모델 이름의 답. 모르는 이름이면 기본 답이다."""
    return REPLIES.get(model, DEFAULT_REPLY)


def pieces(text: str, size: int = PIECE_SIZE) -> list[str]:
    """답을 흘려 보낼 조각들. 이어 붙이면 답과 같다."""
    return [text[start : start + size] for start in range(0, len(text), size)] or ['']


def usage_of(prompt: str, text: str) -> dict:
    """토큰 수. 진짜로 세지 않고 글자 수로 어림한다. 서버는 이 수를 기록하고 값을 매길 뿐이다."""
    return {'prompt_tokens': max(1, len(prompt) // 4), 'completion_tokens': max(1, len(text) // 4)}


def prompt_of(body: dict) -> str:
    """요청의 메시지들을 이어 붙인 글. 토큰 수를 어림하는 데만 쓴다."""
    messages = body.get('messages') or []
    return ''.join(str(message.get('content') or '') for message in messages if isinstance(message, dict))


def stream_events(model: str, text: str, prompt: str) -> Iterator[dict]:
    """흘려 보낼 조각들(JSON). 글 조각들, 멈춘 이유, 토큰 수 차례다."""
    for piece in pieces(text):
        yield {'model': model, 'choices': [{'index': 0, 'delta': {'content': piece}, 'finish_reason': None}]}
    yield {'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]}
    yield {'model': model, 'choices': [], 'usage': usage_of(prompt, text)}


def completion_body(model: str, text: str, prompt: str) -> dict:
    """흘려 보내지 않는 요청의 답 하나."""
    message = {'role': 'assistant', 'content': text}
    return {
        'model': model,
        'choices': [{'index': 0, 'message': message, 'finish_reason': 'stop'}],
        'usage': usage_of(prompt, text),
    }


class Recorder:
    """받은 요청의 모델 이름. 여러 요청이 함께 와도 섞이지 않게 잠근다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._models: deque[str] = deque(maxlen=REMEMBERED)

    def add(self, model: str) -> None:
        with self._lock:
            self._models.append(model)

    def models(self) -> list[str]:
        with self._lock:
            return list(self._models)


def handler_for(recorder: Recorder, delay: float) -> type[BaseHTTPRequestHandler]:
    """요청을 받는 처리기. 받은 요청을 recorder 에 적고, 흘려 보낼 때 조각 사이를 delay 초 쉰다."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == '/health':
                self.send_text(200, 'ok')
            elif self.path == '/v1/requests':
                self.send_json(200, {'models': recorder.models()})
            else:
                self.send_text(404, 'not found')

        def do_POST(self) -> None:
            if self.path.rstrip('/') != '/v1/chat/completions':
                self.send_text(404, 'not found')
                return
            body = self.read_json()
            if body is None:
                self.send_json(400, {'error': {'message': '본문이 JSON 이 아니다'}})
                return
            model = str(body.get('model') or '')
            recorder.add(model)
            text, prompt = reply_for(model), prompt_of(body)
            if body.get('stream'):
                self.send_stream(stream_events(model, text, prompt))
            else:
                self.send_json(200, completion_body(model, text, prompt))

        def read_json(self) -> dict | None:
            length = int(self.headers.get('Content-Length') or 0)
            try:
                body = json.loads(self.rfile.read(length) or b'{}')
            except ValueError:
                return None
            return body if isinstance(body, dict) else None

        def send_stream(self, events: Iterator[dict]) -> None:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            for event in events:
                self.wfile.write(f'data: {json.dumps(event, ensure_ascii=False)}\n\n'.encode())
                self.wfile.flush()
                time.sleep(delay)
            self.wfile.write(b'data: [DONE]\n\n')
            self.wfile.flush()
            self.close_connection = True

        def send_json(self, status: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def send_text(self, status: int, text: str) -> None:
            data = text.encode()
            self.send_response(status)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args) -> None:
            # 요청마다 한 줄. compose 의 로그에서 무엇을 불렀는지 본다
            sys.stderr.write(f'stub-llm {self.command} {self.path} {args[1] if len(args) > 1 else ""}\n')

    return Handler


def build_server(host: str, port: int, delay: float) -> ThreadingHTTPServer:
    """가짜 모델의 서버. 요청마다 스레드 하나다(여러 서버가 함께 부른다)."""
    return ThreadingHTTPServer((host, port), handler_for(Recorder(), delay))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='종단간 테스트의 가짜 언어 모델(OpenAI 호환)')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=11434)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    delay = float(os.environ.get('STUB_LLM_DELAY', DEFAULT_DELAY))
    server = build_server(args.host, args.port, delay)
    print(f'stub-llm 이 {args.host}:{args.port} 에서 듣는다', flush=True)
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
