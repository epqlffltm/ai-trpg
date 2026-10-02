# auth-server/config/test_runner.py

"""
테스트 실행기.

테스트에서만 가벼운 비밀번호 해셔를 쓴다. 기본 해셔는 일부러 느리게 만든 계산이라,
가입과 로그인을 수백 번 하는 테스트에서는 실행 시간의 대부분을 차지한다.

settings.py 에 조건문으로 넣지 않는다. 설정 파일에 약한 해셔가 적혀 있으면
조건이 잘못됐을 때 운영 서버가 그것을 쓰게 된다. 이 파일은 manage.py test 로만 실행된다.
"""

from django.test.runner import DiscoverRunner
from django.test.utils import override_settings

# 강도가 없는 해셔다. 테스트 밖에서 쓰면 안 된다
FAST_PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']


class FastHasherTestRunner(DiscoverRunner):
    """테스트가 도는 동안만 PASSWORD_HASHERS 를 가벼운 해셔로 바꾼다."""

    def setup_test_environment(self, **kwargs) -> None:
        super().setup_test_environment(**kwargs)
        self._hasher_override = override_settings(PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
        self._hasher_override.enable()

    def teardown_test_environment(self, **kwargs) -> None:
        self._hasher_override.disable()
        super().teardown_test_environment(**kwargs)