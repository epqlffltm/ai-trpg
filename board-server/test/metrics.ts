// board-server/test/metrics.ts

/**
 * 테스트가 센 메트릭을 읽는 도구. 부를 때 모으는 것(MetricReader)을 끼우고(metrics.useMeter),
 * 끝나면 아무것도 하지 않는 것으로 되돌린다.
 *
 * 보내는 일(OTLP)은 하지 않는다. 보내는 길은 src/observability/metrics.spec.ts 와 tracing-export.e2e-spec.ts 가 본다.
 * 이름은 계측기의 이름이다(http_server_requests). Prometheus 의 이름(_total, _seconds)은 Alloy 가 붙인다.
 * 테스트마다 새로 끼운다(recordMetrics). 셈은 쌓이는 값이라 앞 테스트의 것이 섞이지 않게 한다.
 */

import { Attributes } from '@opentelemetry/api';
import {
  DataPointType,
  MeterProvider,
  MetricReader,
} from '@opentelemetry/sdk-metrics';
import { useMeter, useNoopMeter } from '../src/observability/metrics.js';

/** 부를 때만 모으는 것. 따로 내보내지 않는다. */
class OnDemandReader extends MetricReader {
  protected onForceFlush(): Promise<void> {
    return Promise.resolve();
  }

  protected onShutdown(): Promise<void> {
    return Promise.resolve();
  }
}

/** 메트릭의 점 하나. label 과 값(셈은 그 수, 히스토그램은 잰 횟수), 단위, 히스토그램의 구간. */
export interface Point {
  labels: Attributes;
  value: number;
  unit: string;
  boundaries?: number[];
}

/** 테스트 하나가 센 메트릭을 모은다. */
export class MetricsRecorder {
  private readonly reader = new OnDemandReader();
  private readonly provider = new MeterProvider({ readers: [this.reader] });

  /** 이것을 끼운다. */
  start(): void {
    useMeter(this.provider.getMeter('board-server'));
  }

  /** 아무것도 하지 않는 것으로 되돌리고 끈다. */
  async stop(): Promise<void> {
    useNoopMeter();
    await this.provider.shutdown();
  }

  /** 그 이름의 점들. */
  async points(name: string): Promise<Point[]> {
    const { resourceMetrics } = await this.reader.collect();
    return resourceMetrics.scopeMetrics.flatMap((scope) =>
      scope.metrics
        .filter((metric) => metric.descriptor.name === name)
        .flatMap((metric) =>
          metric.dataPoints.map((point) =>
            metric.dataPointType === DataPointType.HISTOGRAM
              ? {
                  labels: point.attributes,
                  value: (point.value as { count: number }).count,
                  unit: metric.descriptor.unit,
                  boundaries: (
                    point.value as { buckets: { boundaries: number[] } }
                  ).buckets.boundaries,
                }
              : {
                  labels: point.attributes,
                  value: point.value as number,
                  unit: metric.descriptor.unit,
                },
          ),
        ),
    );
  }

  /** label 이 모두 맞는 점의 값. 없으면 undefined 다. 둘 이상이면 실패한다. */
  async value(
    name: string,
    labels: Attributes = {},
  ): Promise<number | undefined> {
    const found = (await this.points(name)).filter((point) =>
      Object.entries(labels).every(
        ([key, value]) => point.labels[key] === value,
      ),
    );
    expect(found.length).toBeLessThanOrEqual(1);
    return found[0]?.value;
  }
}

/** 테스트마다 새 MetricsRecorder 를 끼우고 끝나면 되돌린다. 돌려준 것의 current 가 지금의 것이다. */
export function recordMetrics(): { current: MetricsRecorder } {
  const holder = { current: new MetricsRecorder() };
  beforeEach(() => {
    holder.current = new MetricsRecorder();
    holder.current.start();
  });
  afterEach(() => holder.current.stop());
  return holder;
}
