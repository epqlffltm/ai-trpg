# auth-server/observability/tracing.py

"""
span 을 OTLP(HTTP)로 수집기(Alloy)에 미는 것을 만든다. 프로세스가 뜰 때 한 번 부른다(observability/apps.py).

보내는 곳은 OTEL_EXPORTER_OTLP_ENDPOINT(경로 없이, http://alloy:4318)다. 다른 서버와 같은 주소다.
비어 있으면 아무것도 만들지 않는다. span 이 생기지 않고, 로그의 trace_id 는 지금처럼 정해진다.
규격은 저장소 루트의 docs/observability.md 의 "3. 추적"에 있다. 알림 서버가 Python 의 본보기다.

모은 span 은 묶어서 보낸다(BatchSpanProcessor, 따로 도는 스레드). 요청은 보내기를 기다리지 않는다.
할 일이 없던 워커의 바퀴는 보내지 않는다(idle_rounds.py).
프로세스가 끝날 때 남은 것을 보낸다(TracerProvider 가 atexit 에 건다). 예약 명령처럼 짧게 도는 것도 남는다.
수집기가 죽어 있어도 서버는 뜨고 요청은 영향을 받지 않는다. 보내지 못한 묶음은 버린다.
"""

import secrets
from urllib.parse import urlsplit

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, Sampler

from observability.formatter import ServiceInfo
from observability.idle_rounds import DropIdleRounds
from observability.spans import use_provider

# OTLP(HTTP)로 추적을 받는 주소의 끝. 보내는 주소 뒤에 붙인다
TRACES_PATH = '/v1/traces'
# 수집기의 답을 기다리는 가장 긴 시간(초). 끌 때 남은 것을 보내는 것도 이만큼에서 포기한다
EXPORT_TIMEOUT_SECONDS = 5
# 수집기의 주소로 받는 앞부분
OTLP_SCHEMES = ('http', 'https')
# span 을 남기는 규칙. 모두 남긴다.
# 부른 쪽의 "기록하지 않음"(traceparent 의 flags 00)을 따르지 않는다. span 을 내보내지 않는 서버는 모두 00 을 보낸다.
# 기본(ParentBased)으로 두면 그 서버가 부른 요청의 span 이 다 버려진다.
# 테스트(observability/tests/spans.py)도 이 규칙을 쓴다
SAMPLER: Sampler = ALWAYS_ON


def otlp_endpoint(value: str) -> str:
    """
    수집기의 주소를 읽는다. 비어 있으면 빈 글자다. 있으면 http:// 나 https:// 로 시작하고 경로가 없어야 한다.

    경로(/v1/traces)는 보내는 쪽이 붙인다. OpenTelemetry 의 OTEL_EXPORTER_OTLP_ENDPOINT 와 같은 뜻이고,
    다른 서버의 같은 설정과 같은 규칙이다. 끝의 / 는 뗀다. 틀리면 ValueError 다(config/settings.py 가 바꿔 올린다).
    """
    written = value.strip()
    if not written:
        return ''
    parts = urlsplit(written)
    if parts.scheme not in OTLP_SCHEMES or not parts.netloc:
        raise ValueError('OTEL_EXPORTER_OTLP_ENDPOINT 는 http:// 나 https:// 로 시작해야 합니다.')
    if parts.path.strip('/') or parts.query or parts.fragment:
        raise ValueError(
            'OTEL_EXPORTER_OTLP_ENDPOINT 는 http://alloy:4318 처럼 경로 없이 적습니다. /v1/traces 는 붙이지 않습니다.'
        )
    return written.rstrip('/')


def instance_id(process: str) -> str:
    """프로세스마다 다른 이름(server-3f2a9c1d, send_outgoing_mail-…). 띄울 때마다 뒤의 글자를 새로 정한다."""
    return f'{process}-{secrets.token_hex(4)}'


def build_resource(info: ServiceInfo, process: str) -> Resource:
    """
    span 과 메트릭의 출처. 서비스, 버전, 환경, 프로세스다. 다른 서버와 같은 이름이다.
    프로세스가 뜰 때 한 번 만들어 둘이 함께 쓴다(observability/apps.py). 그래야 service.instance.id 가 같다.

    정한 넷만 싣는다. Resource.create 는 환경 변수(OTEL_RESOURCE_ATTRIBUTES)와 SDK 의 정보까지 붙인다.
    """
    return Resource(
        {
            'service.name': info.service,
            'service.version': info.version,
            'deployment.environment.name': info.environment,
            'service.instance.id': instance_id(process),
        }
    )


def build_provider(endpoint: str, resource: Resource) -> TracerProvider | None:
    """span 을 보내는 TracerProvider 를 만든다. 보낼 곳이 없으면 None 이다. 만드는 것만으로는 수집기에 닿지 않는다."""
    if not endpoint:
        return None
    provider = TracerProvider(resource=resource, sampler=SAMPLER)
    exporter = OTLPSpanExporter(endpoint=endpoint + TRACES_PATH, timeout=EXPORT_TIMEOUT_SECONDS)
    batch = BatchSpanProcessor(exporter, export_timeout_millis=EXPORT_TIMEOUT_SECONDS * 1000)
    provider.add_span_processor(DropIdleRounds(batch))
    return provider


def configure_tracing(endpoint: str, resource: Resource) -> TracerProvider | None:
    """
    보낼 곳이 있으면 span 을 보내는 것을 만들어 끼운다(spans.use_provider). 만든 것을 돌려준다. 없으면 None 이다.

    보낼 곳이 없으면 끼워 둔 것을 건드리지 않는다. 테스트가 끼운 것(메모리에 모으는 것)이 그대로 남는다.
    """
    provider = build_provider(endpoint, resource)
    if provider is not None:
        use_provider(provider)
    return provider
