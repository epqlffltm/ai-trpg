# auth-server/config/tests/test_api_docs.py

"""
API 목록(OpenAPI, #558)을 확인한다.

  - 목록을 만들 때 경고가 없다. 모양을 적지 않은 뷰가 있으면 실패한다(docs/api/auth.openapi.json 을 뽑는 명령과 같다)
  - 목록의 주소(openapi.json, docs)는 개발(DEBUG)에서만 열린다. 테스트는 DEBUG 가 꺼진 채 돈다
  - 테스트가 받은 응답을 목록과 견주는 것(config/schema_check.py)이 틀린 응답을 잡고, 정한 것은 보지 않는다

응답을 견주는 일 자체는 모든 HTTP 테스트가 한다(config/test_runner.py). 여기서는 그 검사가 제대로 서는지만 본다.
"""

import io

from django.core.management import call_command
from django.http import StreamingHttpResponse
from django.test import Client, TestCase

from config.schema_check import SchemaMismatchError, build_openapi, check_response, start_checking

JWKS_URL = '/api/v1/auth/jwks'


class SchemaGenerationTests(TestCase):
    def test_every_view_has_its_shapes_written(self):
        # 경고가 있으면 CommandError(SchemaGenerationError)로 멈춘다. 모양을 적지 않은 뷰, 이름이 겹친 모양 등
        output = io.StringIO()

        call_command('spectacular', '--format', 'openapi-json', '--validate', '--fail-on-warn', stdout=output)

        self.assertIn('"/api/v1/auth/login"', output.getvalue())

    def test_the_list_is_closed_outside_debug(self):
        # 운영 서버는 API 의 구조를 내보이지 않는다. 저장소의 파일(docs/api/auth.openapi.json)로만 나간다
        for path in ('/api/v1/auth/openapi.json', '/api/v1/auth/docs'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)


class ResponseCheckTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.openapi = build_openapi()

    def test_a_response_that_does_not_match_is_caught(self):
        response = self.client.get(JWKS_URL)
        response.content = b'{"keys": "not-a-list"}'

        with self.assertRaisesMessage(SchemaMismatchError, f'GET {JWKS_URL} 의 응답(200)'):
            check_response(self.openapi, response)

    def test_an_undocumented_status_is_caught(self):
        response = self.client.get(JWKS_URL)
        response.status_code = 418

        with self.assertRaises(SchemaMismatchError):
            check_response(self.openapi, response)

    def test_a_server_error_is_not_checked(self):
        # 어느 주소든 낼 수 있고 본문은 Django 의 기본 오류 화면이라 목록에 적지 않는다
        response = self.client.get(JWKS_URL)
        response.status_code = 500
        response.content = b'<h1>Server Error (500)</h1>'

        check_response(self.openapi, response)

    def test_an_address_outside_the_list_is_not_checked(self):
        # 관리자 화면은 DRF 의 뷰가 아니라 목록에 없다
        response = self.client.get('/admin/login/')

        check_response(self.openapi, response)

    def test_a_streamed_response_is_not_checked(self):
        response = self.client.get(JWKS_URL)
        streamed = StreamingHttpResponse(iter([b'{}']))
        streamed.wsgi_request = response.wsgi_request

        check_response(self.openapi, streamed)

    def test_stopping_puts_the_client_back(self):
        original = Client.request
        stop = start_checking(self.openapi)

        self.assertIsNot(Client.request, original)
        stop()
        self.assertIs(Client.request, original)
