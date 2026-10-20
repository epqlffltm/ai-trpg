# auth-server/gunicorn.conf.py

"""
운영에서 인증 서버를 띄우는 gunicorn 의 설정. gunicorn 은 띄운 폴더의 이 파일을 저절로 읽는다.

개발 중에는 runserver 를 쓰고 이 파일을 읽지 않는다. 컨테이너(Dockerfile)가 gunicorn 으로 띄운다.

    gunicorn config.wsgi

프로세스 수는 WEB_CONCURRENCY 로 정한다. gunicorn 이 그 환경 변수를 저절로 읽는다. 적지 않으면 1 이다.

gunicorn 이 스스로 남기는 줄(뜨고 꺼지는 것, 워커가 죽은 것)도 공통 규격의 JSON 으로 나가게 한다.
Django 의 로그 설정은 워커가 앱을 불러올 때 걸린다. 그 전에 gunicorn 이 남기는 줄은 여기서 걸어야 같은 모양이 된다.
"""

import os

from observability.formatter import ServiceInfo
from observability.setup import SERVICE_NAME, logging_settings

# gunicorn 이 스스로 남기는 줄의 로거와 요청마다 한 줄씩 남기는 로거
GUNICORN_ERROR_LOGGER = 'gunicorn.error'
GUNICORN_ACCESS_LOGGER = 'gunicorn.access'

# 컨테이너 안에서 모든 주소로 받는다. 밖에 여는 포트는 compose 가 정한다
bind = '0.0.0.0:8000'

# 앱(Django)을 워커가 갈라진 뒤에 불러온다. 앱이 뜰 때 span 과 메트릭을 보내는 스레드를 띄운다(observability/apps.py).
# 갈라지기 전에 불러오면(True) 그 스레드가 워커에 따라오지 않아 워커의 span 과 메트릭이 조용히 아무 데도 가지 않는다
preload_app = False

# 요청마다 한 줄은 남기지 않는다. 같은 일을 이 서버의 미들웨어가 공통 규격으로 한다.
# gunicorn 의 줄에는 실제 주소가 주소 뒤에 붙은 값까지 그대로 적힌다
accesslog = None


def gunicorn_logging() -> dict:
    """
    gunicorn 의 로그 설정. Django 와 같은 설정(observability/setup.py)에 gunicorn 의 로거 둘을 더한다.

    환경의 이름과 버전은 설정 파일(config/settings.py)과 같은 환경 변수에서 읽는다. 값이 틀렸으면 워커가 앱을
    불러올 때 설정 파일이 거절한다. 여기서 다시 검사하지 않는다.
    """
    settings = logging_settings(
        ServiceInfo(
            service=SERVICE_NAME,
            environment=os.environ.get('APP_ENVIRONMENT', 'development'),
            version=os.environ.get('APP_VERSION', 'dev'),
        ),
        os.environ.get('LOG_LEVEL', 'info'),
    )
    # gunicorn 이 제 처리기를 달아 둔 로거다. 이름을 적으면 그 처리기를 떼고 맨 위 로거의 JSON 처리기로 올려 보낸다
    settings['loggers'][GUNICORN_ERROR_LOGGER] = {'propagate': True}
    settings['loggers'][GUNICORN_ACCESS_LOGGER] = {'handlers': ['null'], 'propagate': False}
    return settings


logconfig_dict = gunicorn_logging()
