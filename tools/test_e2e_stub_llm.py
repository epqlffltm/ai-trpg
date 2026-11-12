# tools/test_e2e_stub_llm.py

"""
종단간 테스트의 가짜 언어 모델(e2e/stub_llm.py)을 본다. 서버들이 읽는 모양(ai_core/streaming.py)과 맞아야 한다.

    사용: python3 -m unittest discover -s tools -p 'test_e2e_stub_llm.py'
"""

import json
import threading
import unittest
import urllib.request

from e2e import stub_llm


def post(url: str, body: dict) -> tuple[str, bytes]:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method='POST')
    request.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.headers.get('Content-Type', ''), response.read()


def data_lines(raw: bytes) -> list[str]:
    """SSE 의 데이터 줄들."""
    return [line.removeprefix('data: ') for line in raw.decode().splitlines() if line.startswith('data: ')]


class StubServerTests(unittest.TestCase):
    def setUp(self):
        self.server = stub_llm.build_server('127.0.0.1', 0, delay=0)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'

    def test_a_stream_ends_with_usage_and_done(self):
        kind, raw = post(f'{self.base}/v1/chat/completions', {'model': 'e2e-narrator', 'stream': True, 'messages': []})

        lines = data_lines(raw)
        events = [json.loads(line) for line in lines[:-1]]
        text = ''.join(event['choices'][0]['delta'].get('content', '') for event in events if event['choices'])
        self.assertTrue(kind.startswith('text/event-stream'))
        self.assertEqual(text, stub_llm.NARRATION)
        self.assertGreater(len(events), 3)
        self.assertEqual(events[-2]['choices'][0]['finish_reason'], 'stop')
        self.assertEqual(set(events[-1]['usage']), {'prompt_tokens', 'completion_tokens'})
        self.assertEqual(lines[-1], '[DONE]')

    def test_a_plain_request_gets_one_answer(self):
        _, raw = post(f'{self.base}/v1/chat/completions', {'model': 'unknown', 'messages': [{'content': 'hi'}]})

        body = json.loads(raw)
        self.assertEqual(body['choices'][0]['message']['content'], stub_llm.DEFAULT_REPLY)
        self.assertEqual(body['choices'][0]['finish_reason'], 'stop')

    def test_the_called_models_are_remembered(self):
        post(f'{self.base}/v1/chat/completions', {'model': 'e2e-narrator', 'messages': []})

        with urllib.request.urlopen(f'{self.base}/v1/requests', timeout=10) as response:
            self.assertEqual(json.loads(response.read()), {'models': ['e2e-narrator']})

    def test_health(self):
        with urllib.request.urlopen(f'{self.base}/health', timeout=10) as response:
            self.assertEqual(response.read(), b'ok')


class PieceTests(unittest.TestCase):
    def test_pieces_join_back_to_the_reply(self):
        self.assertEqual(''.join(stub_llm.pieces(stub_llm.NARRATION)), stub_llm.NARRATION)
        self.assertEqual(stub_llm.pieces(''), [''])


if __name__ == '__main__':
    unittest.main()
