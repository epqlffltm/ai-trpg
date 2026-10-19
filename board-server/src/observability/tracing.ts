// board-server/src/observability/tracing.ts

/**
 * span 을 OTLP(HTTP)로 수집기(Alloy)에 미는 것을 만든다. 서버가 뜰 때 한 번 부른다(main.ts).
 *
 * 보내는 곳은 OTEL_EXPORTER_OTLP_ENDPOINT(경로 없이, http://alloy:4318)다. 다른 서버와 같은 주소다.
 * 비어 있으면 아무것도 만들지 않는다. span 이 생기지 않고, 로그의 trace_id 는 지금처럼 정해진다.
 * 규격은 저장소 루트의 docs/observability.md 의 "3. 추적"에 있다.
 *
 * 모은 span 은 묶어서 보낸다(BatchSpanProcessor, 타이머로 5초마다). 요청은 보내기를 기다리지 않는다.
 * 할 일이 없던 작업의 바퀴는 보내지 않는다(idle-rounds.ts).
 * 앱이 닫힐 때 남은 것을 보낸다(shutdownTracing, observability.module.ts). 수집기가 죽어 있어도 서버는 뜨고
 * 요청은 영향을 받지 않는다. 보내지 못한 묶음은 버린다.
 */

import { randomBytes } from 'node:crypto';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-proto';
import { Resource, resourceFromAttributes } from '@opentelemetry/resources';
import {
  AlwaysOnSampler,
  BatchSpanProcessor,
  Sampler,
  TracerProvider,
} from '@opentelemetry/sdk-trace';
import { DropIdleRounds } from './idle-rounds.js';
import { ServiceInfo } from './json-logger.js';
import { useProvider } from './spans.js';

/** OTLP(HTTP)로 추적을 받는 주소의 끝. 보내는 주소 뒤에 붙인다 */
export const TRACES_PATH = '/v1/traces';
/** 수집기의 답을 기다리는 가장 긴 시간(밀리초). 닫을 때 남은 것을 보내는 것도 이만큼에서 포기한다 */
export const EXPORT_TIMEOUT_MS = 5000;
/** 서버의 프로세스 이름. service.instance.id 의 앞부분이 된다(server-3f2a9c1d) */
export const SERVER_PROCESS = 'server';
/**
 * span 을 남기는 규칙. 모두 남긴다.
 * 부른 쪽의 "기록하지 않음"(traceparent 의 flags 00)을 따르지 않는다. 다른 서버들과 같은 규칙이다.
 * 기본(ParentBased)으로 두면 flags 00 으로 부른 요청의 span 이 다 버려진다
 */
export const SAMPLER: Sampler = new AlwaysOnSampler();

/** 서버가 뜰 때 만든 것. 닫을 때 남은 것을 보내고 끈다 */
let configured: TracerProvider | undefined;

/** 프로세스마다 다른 이름(server-3f2a9c1d). 띄울 때마다 뒤의 글자를 새로 정한다. */
export function instanceId(processName: string): string {
  return `${processName}-${randomBytes(4).toString('hex')}`;
}

/**
 * span 의 출처. 서비스, 버전, 환경, 프로세스다. 다른 서버와 같은 이름이다.
 *
 * 정한 넷만 싣는다. 환경 변수(OTEL_RESOURCE_ATTRIBUTES)와 호스트의 정보는 읽지 않는다.
 */
export function buildResource(
  info: ServiceInfo,
  processName: string,
): Resource {
  return resourceFromAttributes({
    'service.name': info.service,
    'service.version': info.version,
    'deployment.environment.name': info.environment,
    'service.instance.id': instanceId(processName),
  });
}

/** span 을 보내는 TracerProvider 를 만든다. 보낼 곳이 없으면 undefined 다. 만드는 것만으로는 수집기에 닿지 않는다. */
export function buildProvider(
  endpoint: string,
  info: ServiceInfo,
  processName: string = SERVER_PROCESS,
): TracerProvider | undefined {
  if (endpoint === '') {
    return undefined;
  }
  const exporter = new OTLPTraceExporter({
    url: endpoint + TRACES_PATH,
    timeoutMillis: EXPORT_TIMEOUT_MS,
  });
  const batch = new BatchSpanProcessor({
    exporter,
    exportTimeoutMillis: EXPORT_TIMEOUT_MS,
  });
  return new TracerProvider({
    resource: buildResource(info, processName),
    sampler: SAMPLER,
    spanProcessors: [new DropIdleRounds(batch)],
  });
}

/**
 * 보낼 곳이 있으면 span 을 보내는 것을 만들어 끼운다(spans.useProvider). 만든 것을 돌려준다. 없으면 undefined 다.
 *
 * 보낼 곳이 없으면 끼워 둔 것을 건드리지 않는다. 테스트가 끼운 것(메모리에 모으는 것)이 그대로 남는다.
 */
export function configureTracing(
  endpoint: string,
  info: ServiceInfo,
  processName: string = SERVER_PROCESS,
): TracerProvider | undefined {
  const provider = buildProvider(endpoint, info, processName);
  if (provider !== undefined) {
    useProvider(provider);
    configured = provider;
  }
  return provider;
}

/** configureTracing 이 만든 것이 모아 둔 span 을 보내고 끈다. 만든 것이 없으면 아무것도 하지 않는다. */
export async function shutdownTracing(): Promise<void> {
  const provider = configured;
  configured = undefined;
  await provider?.shutdown();
}
