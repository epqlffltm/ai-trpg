# asset-server/tests/test_tracing_setup.py

"""
이 서버가 꺼질 때 모아 둔 span 과 메트릭을 수집기에 보내는지 검증한다(app/main.py 의 lifespan).
수집기 대신 이 테스트의 HTTP 서버가 받는다.

보내는 것 자체(주소의 규칙, 출처, 끄기)는 공용 코드의 테스트가 본다(shared/server-core/tests/test_tracing_setup.py).
여기서는 이 서버가 그것을 이 서버의 이름으로 잇는지만 본다.
"""

from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.metrics import NoOpMeterProvider
from server_core.database import create_engine
from server_core.observability.metrics import use_meter_provider
from server_core.observability.spans import use_provider
from server_core.testing.collector import Collector
from server_core.testing.tokens import FakeAuthServer

from app.core.config import Settings
from app.main import create_app
from tests.conftest import make_client, make_test_settings


@pytest.fixture
def restore_provider() -> Iterator[None]:
    """끼운 TracerProvider 와 MeterProvider 를 테스트가 끝나면 아무것도 하지 않는 것으로 되돌린다."""
    yield
    use_provider(trace.NoOpTracerProvider())
    use_meter_provider(NoOpMeterProvider())


@pytest.mark.usefixtures('restore_provider')
async def test_shutting_down_the_server_sends_what_is_left(
    collector: tuple[Collector, str], auth_server: FakeAuthServer
):
    received, endpoint = collector
    settings = make_test_settings(otel_exporter_otlp_endpoint=endpoint)
    engine = create_engine(settings)
    app = create_app(settings, http_client=auth_server.make_client(), engine=engine)

    async with app.router.lifespan_context(app), make_client(app) as client:
        await client.get('/api/v1/asset/me')

    assert 'GET /api/v1/asset/me' in received.span_names()
    assert 'http_server_requests' in received.metric_names()
    # FastAPI 가 스스로 내보내는 것(span, 메트릭, 로그)은 없다. 우리가 만든 것만 간다
    assert set(received.paths) == {'/v1/traces', '/v1/metrics'}
    assert all(scope.scope.name == 'asset-server' for scope in received.scopes())
    assert all(scope.scope.name == 'asset-server' for scope in received.metric_scopes())
    assert received.resource()['service.name'] == 'asset-server'
    # span 과 메트릭이 한 출처다(같은 service.instance.id)
    assert received.resource() == received.metric_resource()


def test_the_server_name_is_the_one_in_the_specification():
    # 로그의 service 칸과 span, 메트릭의 출처가 된다. 바뀌면 대시보드와 경보가 이 서버를 잃는다(docs/observability.md)
    assert Settings.service_name == 'asset-server'
