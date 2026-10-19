# notification-server/app/observability/tracing.py

"""
span 을 OTLP(HTTP)로 수집기(Alloy)에 미는 것을 만든다. 서버가 뜰 때 한 번 부른다(app/main.py).

보내는 곳은 OTEL_EXPORTER_OTLP_ENDPOINT(경로 없이, http://alloy:4318)다. 다른 서버의 메트릭과 같은 주소다.
비어 있으면 아무것도 만들지 않는다. span 이 생기지 않고, 로그의 trace_id 는 지금처럼 정해진다.
규격은 저장소 루트의 docs/observability.md 의 "3. 추적"에 있다. 결제 서버(Go)가 본보기다.

모은 span 은 묶어서 보낸다(BatchSpanProcessor, 따로 도는 스레드). 요청은 보내기를 기다리지 않는다.
수집기가 죽어 있어도 서버는 뜨고 요청은 영향을 받지 않는다. 보내지 못한 묶음은 버린다.
"""

import secrets

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, Sampler

from app.core.config import Settings
from app.observability.setup import SERVICE_NAME
from app.observability.spans import use_provider

# OTLP(HTTP)로 추적을 받는 주소의 끝. 보내는 주소 뒤에 붙인다
TRACES_PATH = '/v1/traces'
# 수집기의 답을 기다리는 가장 긴 시간(초). 끌 때 남은 것을 보내는 것도 이만큼에서 포기한다
EXPORT_TIMEOUT_SECONDS = 5
# 이 서버의 프로세스 이름. service.instance.id 의 앞부분이 된다(server-3f2a9c1d). 결제 서버와 같은 모양이다
SERVER_PROCESS = 'server'
# span 을 남기는 규칙. 모두 남긴다.
# 부른 쪽의 "기록하지 않음"(traceparent 의 flags 00)을 따르지 않는다. span 을 내보내지 않는 서버는 모두 00 을 보낸다.
# 기본(ParentBased)으로 두면 그 서버가 부른 요청의 span 이 다 버려진다. 테스트(tests/spans.py)도 이 규칙을 쓴다
SAMPLER: Sampler = ALWAYS_ON


def instance_id(process: str) -> str:
    """프로세스마다 다른 이름. 띄울 때마다 뒤의 글자를 새로 정한다. 같으면 두 프로세스의 span 이 한 출처로 보인다."""
    return f'{process}-{secrets.token_hex(4)}'


def build_resource(settings: Settings, process: str) -> Resource:
    """
    span 의 출처. 서비스, 버전, 환경, 프로세스다. 결제 서버의 메트릭과 추적이 쓰는 이름과 같다.

    정한 넷만 싣는다. Resource.create 는 환경 변수(OTEL_RESOURCE_ATTRIBUTES)와 SDK 의 정보까지 붙인다.
    """
    return Resource(
        {
            'service.name': SERVICE_NAME,
            'service.version': settings.app_version,
            'deployment.environment.name': settings.app_environment,
            'service.instance.id': instance_id(process),
        }
    )


def build_provider(settings: Settings, process: str = SERVER_PROCESS) -> TracerProvider | None:
    """span 을 보내는 TracerProvider 를 만든다. 보낼 곳이 없으면 None 이다. 만드는 것만으로는 수집기에 닿지 않는다."""
    endpoint = settings.otel_exporter_otlp_endpoint
    if not endpoint:
        return None
    provider = TracerProvider(resource=build_resource(settings, process), sampler=SAMPLER)
    exporter = OTLPSpanExporter(endpoint=endpoint + TRACES_PATH, timeout=EXPORT_TIMEOUT_SECONDS)
    provider.add_span_processor(BatchSpanProcessor(exporter, export_timeout_millis=EXPORT_TIMEOUT_SECONDS * 1000))
    return provider


def configure_tracing(settings: Settings) -> TracerProvider | None:
    """
    보낼 곳이 있으면 span 을 보내는 것을 만들어 끼운다(spans.use_provider). 만든 것을 돌려준다. 없으면 None 이다.

    보낼 곳이 없으면 끼워 둔 것을 건드리지 않는다. 테스트가 끼운 것(메모리에 모으는 것)이 그대로 남는다.
    """
    provider = build_provider(settings)
    if provider is not None:
        use_provider(provider)
    return provider


def shutdown_tracing(provider: TracerProvider | None) -> None:
    """
    모아 둔 span 을 보내고 끈다. 서버가 꺼질 때 부른다. 보낼 것을 기다리느라 막히므로 스레드에서 부른다(app/main.py).

    수집기가 답하지 않으면 EXPORT_TIMEOUT_SECONDS 뒤에 버리고 끈다.
    """
    if provider is not None:
        provider.shutdown()
