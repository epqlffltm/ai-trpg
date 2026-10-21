# tools/test_export_openapi.py

"""
OpenAPI 를 뽑아 docs/api/ 에 두는 도구(export_openapi.py)를 본다. 서버를 부르지 않고 가짜 OpenAPI 를 넣어 본다.
진짜 서버에서 뽑는 것은 CI 의 api-docs 가 한다(.github/workflows/ci.yml).

    사용: python3 -m unittest discover -s tools -p 'test_export_openapi.py'
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import export_openapi
from export_openapi import (
    SOURCES,
    Source,
    audience_of,
    command_env,
    fastapi_source,
    go_source,
    mark_audience,
    nest_source,
    parse_args,
    render,
    resolve_command,
    run,
    target_path,
)


def fake_spec() -> dict:
    """작은 OpenAPI. 사용자, 서버끼리, 운영자, 웹훅, 상태 확인의 주소가 하나씩 있다."""
    return {
        'openapi': '3.1.0',
        'info': {'title': '가짜 서버', 'version': '0.1.0'},
        'paths': {
            '/api/v1/x/me': {'get': {'summary': '나'}},
            '/api/v1/x/service/{source}/things': {'post': {}},
            '/api/v1/x/admin/users/{id}': {'get': {}, 'parameters': [{'name': 'id', 'in': 'path'}]},
            '/api/v1/x/webhooks/payment': {'post': {}},
            '/health': {'get': {}},
        },
    }


class AudienceTests(unittest.TestCase):
    def test_paths_are_sorted_by_who_calls_them(self):
        self.assertEqual(audience_of('/api/v1/x/me'), 'user')
        self.assertEqual(audience_of('/api/v1/notification/service/game/notifications'), 'service')
        self.assertEqual(audience_of('/api/v1/game/admin/tables/{table_id}'), 'operator')
        self.assertEqual(audience_of('/api/v1/billing/webhooks/payment'), 'webhook')
        self.assertEqual(audience_of('/health/ready'), 'infra')

    def test_every_operation_gets_a_mark_but_not_the_path_parameters(self):
        # 주소 칸 아래의 parameters 는 요청 방식이 아니다. 거기에 적으면 OpenAPI 가 깨진다
        spec = mark_audience(fake_spec())

        self.assertEqual(spec['paths']['/api/v1/x/me']['get']['x-audience'], 'user')
        self.assertEqual(spec['paths']['/api/v1/x/service/{source}/things']['post']['x-audience'], 'service')
        self.assertEqual(spec['paths']['/api/v1/x/admin/users/{id}']['get']['x-audience'], 'operator')
        self.assertIsInstance(spec['paths']['/api/v1/x/admin/users/{id}']['parameters'], list)

    def test_a_mark_the_server_wrote_is_kept(self):
        # 게시판의 운영자 API 는 주소에 /admin/ 이 없다. 서버가 적은 operator 를 주소의 모양(user)으로 덮으면 안 된다
        spec = fake_spec()
        spec['paths']['/api/v1/x/me']['get']['x-audience'] = 'operator'

        marked = mark_audience(spec)

        self.assertEqual(marked['paths']['/api/v1/x/me']['get']['x-audience'], 'operator')


class RenderTests(unittest.TestCase):
    def test_same_content_gives_the_same_text_whatever_the_key_order(self):
        # 서버가 키를 다른 차례로 내도 파일은 같아야 CI 가 엉뚱하게 실패하지 않는다
        first = {'b': 1, 'a': {'d': 2, 'c': 3}}
        second = {'a': {'c': 3, 'd': 2}, 'b': 1}

        self.assertEqual(render(first), render(second))

    def test_keeps_korean_and_ends_with_one_newline(self):
        text = render({'title': '게임 서버'})

        self.assertIn('게임 서버', text)
        self.assertTrue(text.endswith('}\n'))
        self.assertFalse(text.endswith('\n\n'))


class SourceTests(unittest.TestCase):
    def test_fastapi_servers_are_listed(self):
        self.assertEqual(SOURCES['trpg'].folder, 'trpg-server')
        self.assertEqual(SOURCES['notification'].folder, 'notification-server')
        self.assertEqual(SOURCES['asset'], fastapi_source('asset-server'))

    def test_the_billing_server_reads_its_written_spec(self):
        self.assertEqual(SOURCES['billing'], go_source('billing-server'))
        self.assertEqual(SOURCES['billing'].command, ('go', 'run', './cmd/openapi'))
        self.assertEqual(SOURCES['billing'].env, ())

    def test_the_board_server_builds_and_prints_its_spec(self):
        self.assertEqual(SOURCES['board'], nest_source('board-server'))
        self.assertEqual(SOURCES['board'].command, ('npm', 'run', '--silent', 'openapi'))

    def test_the_board_server_gets_a_database_address_node_can_read(self):
        # Node 의 pg 는 postgresql+asyncpg:// 를 읽지 못한다. FastAPI 의 값을 그대로 쓰면 설정을 읽다가 멈춘다
        env = dict(SOURCES['board'].env)

        self.assertTrue(env['DATABASE_URL'].startswith('postgresql://'))
        self.assertTrue(env['AUTH_JWKS_URL'])

    def test_required_settings_are_filled_only_when_missing(self):
        source = fastapi_source('x-server')
        with mock.patch.dict('os.environ', {'DATABASE_URL': 'mine'}, clear=False):
            env = command_env(source)

        self.assertEqual(env['DATABASE_URL'], 'mine')
        self.assertTrue(env['AUTH_JWKS_URL'])

    def test_unknown_server_is_refused(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args(['nope'])


class RunTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.spec = fake_spec()

    def fetch(self, source: Source, root: Path) -> dict:
        return json.loads(json.dumps(self.spec))

    def run_tool(self, check: bool) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return run(['trpg'], self.root, check, fetch=self.fetch)

    def test_writes_the_file_with_marks(self):
        self.assertEqual(self.run_tool(check=False), 0)

        written = json.loads(target_path(self.root, 'trpg').read_text(encoding='utf-8'))
        self.assertEqual(written['paths']['/health']['get']['x-audience'], 'infra')

    def test_check_passes_when_the_file_is_current(self):
        self.run_tool(check=False)

        self.assertEqual(self.run_tool(check=True), 0)

    def test_check_fails_and_writes_nothing_when_the_server_changed(self):
        self.run_tool(check=False)
        before = target_path(self.root, 'trpg').read_text(encoding='utf-8')
        self.spec['paths']['/api/v1/x/new'] = {'get': {}}

        self.assertEqual(self.run_tool(check=True), 1)
        self.assertEqual(target_path(self.root, 'trpg').read_text(encoding='utf-8'), before)

    def test_check_fails_when_the_file_is_missing(self):
        self.assertEqual(self.run_tool(check=True), 1)

    def test_file_uses_lf_even_on_windows(self):
        self.run_tool(check=False)

        self.assertNotIn(b'\r\n', target_path(self.root, 'trpg').read_bytes())


class FetchTests(unittest.TestCase):
    def test_a_failing_server_stops_with_its_error(self):
        source = Source(folder='.', command=('python3', '-c', 'import sys; sys.exit("설정이 틀렸다")'))

        with self.assertRaises(RuntimeError) as caught:
            export_openapi.fetch_spec(source, Path(tempfile.gettempdir()))
        self.assertIn('설정이 틀렸다', str(caught.exception))

    def test_what_a_failing_build_printed_is_shown_too(self):
        # tsc 는 타입 오류를 표준 출력에 낸다. 표준 에러가 비어도 까닭이 보여야 한다
        source = Source(folder='.', command=('python3', '-c', 'import sys; print("타입이 틀렸다"); sys.exit(2)'))

        with self.assertRaises(RuntimeError) as caught:
            export_openapi.fetch_spec(source, Path(tempfile.gettempdir()))
        self.assertIn('타입이 틀렸다', str(caught.exception))


class ResolveCommandTests(unittest.TestCase):
    def test_the_program_becomes_its_path(self):
        # Windows 의 npm 은 npm.cmd 라서 경로로 바꾸어 넘겨야 subprocess 가 찾는다
        with mock.patch('shutil.which', return_value='C:/node/npm.CMD'):
            self.assertEqual(resolve_command(('npm', 'run', 'x')), ('C:/node/npm.CMD', 'run', 'x'))

    def test_an_unknown_program_is_left_as_it_is(self):
        with mock.patch('shutil.which', return_value=None):
            self.assertEqual(resolve_command(('nope', '-v')), ('nope', '-v'))


if __name__ == '__main__':
    unittest.main()
