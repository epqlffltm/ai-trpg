# auth-server/config/test_runner.py

"""
테스트 실행기. 테스트에서만 달라야 하는 설정 세 가지를 바꾼다.

비밀번호 해셔를 가벼운 것으로 바꾼다. 기본 해셔는 일부러 느리게 만든 계산이라,
가입과 로그인을 수백 번 하는 테스트에서는 실행 시간의 대부분을 차지한다.

메일을 발송함에 적지 않고 그 자리에서 보낸다. 테스트에는 워커가 없다.
(Django 는 테스트 중에 메일을 실제로 보내지 않고 mail.outbox 에 쌓는다.)
발송함 자체의 테스트는 이 설정을 다시 outbox 로 바꿔서 한다.

시도 횟수 제한을 끈다. 테스트는 같은 주소(127.0.0.1)에서 로그인을 수백 번 한다.
제한이 켜져 있으면 제한과 상관없는 테스트가 막힌다.
제한 자체의 테스트는 이 설정을 다시 켜고, 키의 앞머리를 바꿔 개발용 횟수와 섞이지 않게 한다.

settings.py 에 조건문으로 넣지 않는다. 설정 파일에 약한 해셔가 적혀 있으면
조건이 잘못됐을 때 운영 서버가 그것을 쓰게 된다. 이 파일은 manage.py test 로만 실행된다.
"""

from django.test.runner import DiscoverRunner
from django.test.utils import override_settings

# 강도가 없는 해셔다. 테스트 밖에서 쓰면 안 된다
FAST_PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']


class FastHasherTestRunner(DiscoverRunner):
    """테스트가 도는 동안만 해셔, 메일 발송 방식, 시도 제한을 바꾼다."""

    def setup_test_environment(self, **kwargs) -> None:
        super().setup_test_environment(**kwargs)
        self._settings_override = override_settings(
            PASSWORD_HASHERS=FAST_PASSWORD_HASHERS,
            MAIL_DELIVERY='inline',
            ATTEMPT_LIMITS_ENABLED=False,
            ATTEMPT_LIMIT_KEY_PREFIX='auth-test:attempts',
        )
        self._settings_override.enable()

    def teardown_test_environment(self, **kwargs) -> None:
        self._settings_override.disable()
        super().teardown_test_environment(**kwargs)
