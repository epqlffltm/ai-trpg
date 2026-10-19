# auth-server/observability/apps.py

"""
관측(로그, 추적)을 프로세스가 뜰 때 건다. Django 가 앱을 불러온 뒤 한 번 부른다(ready).

서버(gunicorn), 워커(관리 명령), 예약 명령이 모두 이 길로 뜬다. 하는 일은 둘이다.
  - 보낼 곳(OTEL_EXPORTER_OTLP_ENDPOINT)이 있으면 span 을 수집기에 민다(tracing.py)
  - DB 연결을 맺을 때마다 쿼리 span 을 단다(db_spans.py)
테스트(manage.py test)는 내보내지 않는다. 개발자의 .env 에 주소가 있어도 그렇다. span 을 보는 테스트는 메모리에 모은다.
"""

import sys
from pathlib import Path

from django.apps import AppConfig
from django.conf import settings
from django.db.backends.signals import connection_created

from observability.db_spans import on_connection_created
from observability.formatter import ServiceInfo
from observability.setup import SERVICE_NAME
from observability.tracing import configure_tracing

# 서버(gunicorn)의 프로세스 이름. service.instance.id 의 앞부분이 된다(server-3f2a9c1d)
SERVER_PROCESS = 'server'
# 테스트를 돌리는 명령. 이 명령에서는 span 을 내보내지 않는다
TEST_COMMAND = 'test'


def process_name(argv: list[str]) -> str:
    """이 프로세스의 이름. 관리 명령이면 그 이름(send_outgoing_mail), 아니면(gunicorn) server 다."""
    if len(argv) > 1 and Path(argv[0]).name == 'manage.py':
        return argv[1]
    return SERVER_PROCESS


def service_info() -> ServiceInfo:
    """설정에서 이 서버가 누구인지를 꺼낸다. 로그와 같은 값이다."""
    return ServiceInfo(service=SERVICE_NAME, environment=settings.APP_ENVIRONMENT, version=settings.APP_VERSION)


def start_tracing(argv: list[str]) -> None:
    """보낼 곳이 있으면 span 을 수집기에 밀기 시작한다. 테스트에서는 하지 않는다."""
    process = process_name(argv)
    if process == TEST_COMMAND:
        return
    configure_tracing(settings.OTEL_EXPORTER_OTLP_ENDPOINT, service_info(), process)


class ObservabilityConfig(AppConfig):
    name = 'observability'

    def ready(self) -> None:
        connection_created.connect(on_connection_created, dispatch_uid='observability.db_spans')
        start_tracing(sys.argv)
