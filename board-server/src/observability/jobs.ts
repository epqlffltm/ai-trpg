// board-server/src/observability/jobs.ts

/**
 * 요청과 따로 도는 작업 한 바퀴를 거는 곳. 작업의 span 과 로그의 job_id 를 함께 건다.
 * 규격은 저장소 루트의 docs/observability.md 의 "작업 식별자 job_id" 와 "3. 추적"에 있다.
 *
 * 바퀴마다 새 job_id 다. span 이 있으면 로그의 trace_id 는 그 span 의 것이고, 없으면(내보내지 않는다) 새로 정한다.
 * 작업 안의 로그에는 job_id 와 trace_id 가 붙고 request_id 는 붙지 않는다.
 * 바퀴마다 작업의 메트릭(background_jobs_*)도 센다(metrics.ts 의 measuredJob). 할 일이 없던 바퀴도 센다.
 */

import { newJobId, newTrace } from './identifiers.js';
import { measuredJob } from './metrics.js';
import { runInJob } from './request-context.js';
import { inJobSpan, spanTrace } from './spans.js';

/**
 * 작업 한 바퀴(work)를 그 span 과 job_id 안에서 돌린다. work 의 결과를 돌려준다.
 *
 * work 가 예외를 내면 span 을 오류로 표시하고 그대로 올린다. 로그는 work 가 남긴다.
 */
export function runAsJob<Result>(
  operation: string,
  work: () => Promise<Result>,
): Promise<Result> {
  const jobId = newJobId();
  return inJobSpan(operation, jobId, () =>
    runInJob({ jobId, trace: spanTrace() ?? newTrace() }, () =>
      measuredJob(operation, work),
    ),
  );
}
