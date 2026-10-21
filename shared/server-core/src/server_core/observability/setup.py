# shared/server-core/src/server_core/observability/setup.py

"""
이 서버의 로그가 공통 규격의 JSON 으로 나가게 건다. 앱을 만들 때 한 번 부른다(서버의 app/main.py).

표준 logging 을 그대로 쓴다. 맨 위(root) 로거에 JSON 으로 적는 처리기를 하나 단다. 그래서 이 서버의 코드든
라이브러리든, logging 으로 남긴 것은 모두 같은 모양으로 나간다.

uvicorn 은 제 로거(uvicorn, uvicorn.error, uvicorn.access)에 제 처리기를 달아 둔다. 그대로 두면 한 서버에서
모양이 다른 로그가 섞여 나온다.
  - uvicorn 과 uvicorn.error 는 제 처리기를 떼고 맨 위 로거로 올려 보낸다. 서버가 뜨고 꺼지는 기록이 JSON 으로 나간다.
  - uvicorn.access(요청마다 한 줄)는 끈다. 같은 일을 이 서버의 미들웨어(middleware.py)가 공통 규격으로 한다.
    uvicorn 의 줄에는 실제 주소가 그대로 적힌다. 주소에는 테이블의 ID 같은 값이 들어 있다.
  - "Exception in ASGI application" 은 버린다. 처리하지 못한 예외는 미들웨어가 식별자와 함께 이미 적었다.
"""

import logging
import sys

from server_core.observability.context import current_ids
from server_core.observability.formatter import CONTEXT_IDS_FIELD, JsonFormatter, ServiceInfo
from server_core.settings import CoreSettings

# 맨 위 로거로 올려 보낼 uvicorn 의 로거들
_UVICORN_LOGGERS = ('uvicorn', 'uvicorn.error')
# 끄는 uvicorn 의 로거
_UVICORN_ACCESS_LOGGER = 'uvicorn.access'
# uvicorn 이 처리하지 못한 예외를 적을 때의 글. 앞부분만 본다
_UVICORN_UNHANDLED = 'Exception in ASGI application'


class JsonLogHandler(logging.StreamHandler):
    """공통 규격으로 적는 처리기. 종류로 알아볼 수 있게 이름만 따로 둔다. 두 번 달지 않으려고 쓴다."""


class DropUnhandledNotice(logging.Filter):
    """uvicorn 이 처리하지 못한 예외를 다시 적는 줄을 버린다. 같은 예외를 미들웨어가 이미 적었다."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not str(record.msg).startswith(_UVICORN_UNHANDLED)


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

    def factory(*args: object, **kwargs: object) -> logging.LogRecord:
        return attach_identifiers(current(*args, **kwargs))

    factory.attaches_identifiers = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)


def service_info(settings: CoreSettings) -> ServiceInfo:
    """설정에서 이 서버가 누구인지를 꺼낸다. 이름은 서버의 설정이 클래스에 적은 것이다(CoreSettings.service_name)."""
    return ServiceInfo(
        service=settings.service_name, environment=settings.app_environment, version=settings.app_version
    )


def has_json_handler(logger: logging.Logger) -> bool:
    """이 로거에 공통 규격의 처리기가 이미 달려 있는가."""
    return any(isinstance(handler, JsonLogHandler) for handler in logger.handlers)


def attach_json_handler(root: logging.Logger, info: ServiceInfo) -> None:
    """
    맨 위 로거에 공통 규격의 처리기를 단다. 이미 달려 있으면 누구인지만 다시 맞춘다.

    다른 처리기는 건드리지 않는다. 테스트 도구(pytest)가 로그를 잡으려고 달아 둔 처리기가 떨어지지 않는다.
    로그는 표준 오류(stderr)로 나간다. 모으는 것은 서버 밖의 일이다.
    """
    for handler in root.handlers:
        if isinstance(handler, JsonLogHandler):
            handler.setFormatter(JsonFormatter(info))
            return
    handler = JsonLogHandler(sys.stderr)
    handler.setFormatter(JsonFormatter(info))
    root.addHandler(handler)


def route_uvicorn_logs() -> None:
    """uvicorn 의 로그를 공통 규격으로 모은다. 요청마다의 줄은 끈다."""
    for name in _UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    error_logger = logging.getLogger('uvicorn.error')
    if not any(isinstance(existing, DropUnhandledNotice) for existing in error_logger.filters):
        error_logger.addFilter(DropUnhandledNotice())
    access_logger = logging.getLogger(_UVICORN_ACCESS_LOGGER)
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True


def configure_logging(settings: CoreSettings) -> None:
    """
    이 서버의 로그를 공통 규격으로 건다. 여러 번 불러도 처리기는 하나다.

    설정의 값은 적지 않는다. 설정에는 DB 주소와 API 키가 들어 있다.
    """
    install_record_factory()
    root = logging.getLogger()
    attach_json_handler(root, service_info(settings))
    root.setLevel(settings.log_level.upper())
    route_uvicorn_logs()
