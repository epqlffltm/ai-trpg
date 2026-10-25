# auth-server/accounts/tests/test_input_errors.py

"""
입력 오류의 본문(accounts/exception_handlers.py)을 검증한다.

  - 칸의 검증(400)은 {"detail", "errors"} 다. 다른 서버들과 같은 모양이다(docs/api/README.md)
  - 칸을 가르지 않는 검증 오류(목록으로 온 것)는 errors 의 non_field_errors 다
  - 입력 칸의 이름이 code 여도 오류의 이름(code)과 섞이지 않는다
"""

from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.exceptions import ValidationError

from accounts.exception_handlers import INVALID_INPUT_DETAIL, handle_exception, input_error_body


class InputErrorBodyTests(SimpleTestCase):
    def test_field_errors_are_wrapped(self):
        self.assertEqual(
            input_error_body({'username': ['이미 사용 중인 아이디입니다.']}),
            {'detail': INVALID_INPUT_DETAIL, 'errors': {'username': ['이미 사용 중인 아이디입니다.']}},
        )

    def test_errors_without_a_field_go_to_non_field_errors(self):
        self.assertEqual(
            input_error_body(['만 14세 이상만 가입할 수 있습니다.']),
            {'detail': INVALID_INPUT_DETAIL, 'errors': {'non_field_errors': ['만 14세 이상만 가입할 수 있습니다.']}},
        )

    def test_a_field_named_code_stays_inside_errors(self):
        response = handle_exception(ValidationError({'code': ['6자리 숫자를 적어 주세요.']}), {})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data), {'detail', 'errors'})
        self.assertEqual(response.data['errors']['code'], ['6자리 숫자를 적어 주세요.'])
