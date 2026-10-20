// board-server/src/observability/observability.module.ts

/**
 * 앱이 닫힐 때 모아 둔 span 과 메트릭을 보내고 끄는 모듈. 켜는 것은 main.ts 다(configureTracing, configureMetrics).
 *
 * 닫힐 때(onApplicationShutdown) 부른다. 서버는 끄라는 신호(SIGTERM)를 받으면 앱을 닫는다(main.ts 의 enableShutdownHooks).
 * 묶어 보내기를 기다리던 span(5초치)이 사라지지 않는다. 테스트가 만든 앱에서는 켠 것이 없어 아무것도 하지 않는다.
 */

import { Injectable, Module, OnApplicationShutdown } from '@nestjs/common';
import { shutdownMetrics } from './metrics.js';
import { shutdownTracing } from './tracing.js';

@Injectable()
export class TelemetryShutdown implements OnApplicationShutdown {
  /** 모아 둔 span 과 메트릭을 보내고 끈다. 수집기가 죽어 있으면 5초씩 기다리고 버린다. 둘을 함께 기다린다. */
  async onApplicationShutdown(): Promise<void> {
    await Promise.all([shutdownTracing(), shutdownMetrics()]);
  }
}

@Module({ providers: [TelemetryShutdown] })
export class ObservabilityModule {}
