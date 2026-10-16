# auth-server/observability/setup.py

"""
이 서버의 로그가 공통 규격의 JSON 으로 나가게 건다. 규격은 docs/observability.md 에 있다.

Django 는 뜰 때 설정의 LOGGING 을 LOGGING_CONFIG 에 적힌 함수에 넘겨 로그를 건다. 그 자리에 configure 를 꽂는다
(config/settings.py). Django 의 기본 함수가 하는 일(logging.config.dictConfig)을 그대로 하고, 하나를 더한다.
logging 이 로그 한 줄을 만들 때마다 지금 걸려 있는 식별자를 붙이게 한다.
"""

import logging
import logging.config

from observability.context import current_ids
from observability.formatter import CONTEXT_IDS_FIELD, ServiceInfo

# 이 서버의 이름. 로그의 service 칸에 들어간다. 규격(docs/observability.md)에 적힌 이름이다
SERVICE_NAME = 'auth-server'
# 요청에 관한 Django 의 로거. 처리하지 못한 예외와 4xx, 5xx 응답을 적는다
DJANGO_REQUEST_LOGGER = 'django.request'
# 개발 서버(runserver)가 요청마다 한 줄씩 적는 로거
DJANGO_SERVER_LOGGER = 'django.server'
# 요청 식별 미들웨어가 "이 예외는 내가 적었다"고 요청에 남기는 표시의 이름
LOGGED_UNHANDLED_ATTRIBUTE = '_observability_logged_unhandled'
# 서버의 잘못으로 보는 상태 코드의 시작
SERVER_ERROR = 500


def attach_identifiers(record: logging.LogRecord) -> logging.LogRecord:
    """
    로그 한 줄에 지금 걸려 있는 식별자(request_id, trace_id, job_id)를 붙인다.

    로그가 남는 순간에 붙인다. 나가는 모양으로 바꿀 때(Formatter) 붙이면, 그 일이 다른 자리에서 일어날 때
    (모아 두었다가 따로 내보내는 처리기) 엉뚱한 요청의 식별자가 붙거나 아무것도 붙지 않는다.

    한 칸(context_ids)에 묶어서 붙인다. 식별자의 이름으로 하나씩 붙이면, 같은 이름을 extra 로 넘긴 로그에서
    logging 이 "이미 있는 칸을 덮어쓰려 한다"며 예외를 낸다.
    """
    setattr(record, CONTEXT_IDS_FIELD, current_ids())
    return record


def install_record_factory() -> None:
    """
    logging 이 로그 한 줄을 만들 때마다 식별자를 붙이게 한다. 여러 번 불러도 한 번만 건다.

    logging 에는 "한 줄을 만드는 함수"를 바꿔 끼우는 자리가 있다. 원래의 함수를 감싸서, 만든 줄에 식별자를 붙인다.
    """
    current = logging.getLogRecordFactory()
    if getattr(current, 'attaches_identifiers', False):
        return

    def factory(*args, **kwargs) -> logging.LogRecord:
        return attach_identifiers(current(*args, **kwargs))

    factory.attaches_identifiers = True
    logging.setLogRecordFactory(factory)


class OnlyUnloggedServerErrors(logging.Filter):
    """
    Django 가 요청에 관해 적는 줄 중에서, 다른 곳이 적지 않은 서버의 오류만 남긴다. django.request 로거에 건다.

    Django 는 4xx 와 5xx 응답마다 "Not Found: /주소" 같은 줄을 적는다. 요청이 끝난 줄은 미들웨어가 공통 규격으로
    이미 적는다. Django 의 줄에는 실제 주소가 그대로 들어 있어서 버린다.
    뷰가 스스로 돌려준 5xx(readiness 의 503 같은 것)도 같다. 예외가 없는 줄이라 미들웨어의 줄 말고 더할 것이 없다.
    Django 는 그런 응답을 수준을 가리지 않고 error 로 적는다. 남겨 두면 "준비 안 됨"이 10초마다 error 로 쌓인다.
    뷰에서 난 예외도 미들웨어가 식별자와 함께 적는다. 같은 예외를 Django 가 다시 적는 줄은 버린다.
    남기는 것은 미들웨어가 보지 못한 서버의 예외다. 다른 미들웨어 안에서 난 예외가 그렇다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        status_code = getattr(record, 'status_code', SERVER_ERROR)
        if isinstance(status_code, int) and status_code < SERVER_ERROR:
            return False
        if record.exc_info is None:
            return False
        return not getattr(getattr(record, 'request', None), LOGGED_UNHANDLED_ATTRIBUTE, False)


def logging_settings(info: ServiceInfo, level: str) -> dict:
    """
    설정의 LOGGING 에 넣을 값을 만든다. 로그는 모두 한 처리기를 거쳐 공통 규격의 JSON 으로 표준 오류에 나간다.

      - 맨 위(root) 로거에 처리기를 단다. 이 서버의 코드든 라이브러리든 같은 모양으로 나간다.
      - django.request 는 걸러서 올려 보낸다(OnlyUnloggedServerErrors).
      - django.server(개발 서버의 요청마다 한 줄)는 끈다. 같은 일을 미들웨어가 한다. 그 줄에는 실제 주소가
        주소 뒤에 붙은 값까지 그대로 적힌다.
    """
    return {
        'version': 1,
        # 이미 만들어진 로거를 끄지 않는다. 끄면 이 설정보다 먼저 불려 온 모듈의 로거가 조용히 죽는다
        'disable_existing_loggers': False,
        'formatters': {
            'json': {'()': 'observability.formatter.JsonFormatter', 'info': info},
        },
        'filters': {
            'only_unlogged_server_errors': {'()': 'observability.setup.OnlyUnloggedServerErrors'},
        },
        'handlers': {
            'json': {'class': 'logging.StreamHandler', 'formatter': 'json'},
            # 아무것도 적지 않는 처리기. 처리기가 하나도 없는 로거의 경고는 logging 이 형식 없이 그대로 찍는다.
            # 끄려는 로거에는 이것을 단다
            'null': {'class': 'logging.NullHandler'},
        },
        'root': {'handlers': ['json'], 'level': level.upper()},
        'loggers': {
            DJANGO_REQUEST_LOGGER: {'filters': ['only_unlogged_server_errors'], 'propagate': True},
            DJANGO_SERVER_LOGGER: {'handlers': ['null'], 'propagate': False},
        },
    }


def configure(settings: dict) -> None:
    """설정의 LOGGING 대로 로그를 걸고, 로그 한 줄마다 식별자가 붙게 한다. Django 가 뜰 때 한 번 부른다."""
    install_record_factory()
    logging.config.dictConfig(settings)
