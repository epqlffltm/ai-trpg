// board-server/src/notifications/notification-dispatcher.runner.ts

/**
 * 발송함의 알림을 정해 둔 간격(5초)마다 보낸다. 앱이 뜨면 돌기 시작하고, 닫힐 때 멈춘다.
 *
 * 보내는 일 자체는 NotificationDispatcher 가 한다. 여기는 언제 돌릴지만 정한다.
 * 앞 바퀴가 끝나지 않았으면 다음 바퀴를 건너뛴다. 알림 서버가 느려도 바퀴가 겹쳐 쌓이지 않는다.
 * 바퀴마다 작업의 span 과 job_id 를 건다(observability/jobs.ts). 그 바퀴의 로그에 job_id 와 trace_id 가 붙는다.
 * 처리한 수를 span 에 싣는다. 할 일이 없던 바퀴의 추적은 보내지 않는다(observability/idle-rounds.ts).
 * 타이머는 프로세스를 붙잡지 않는다(unref). 끊긴 세션 목록 받기(auth/session-revocations.refresher.ts)와 같다.
 */

import {
  Injectable,
  Logger,
  OnApplicationBootstrap,
  OnModuleDestroy,
} from '@nestjs/common';
import { runAsJob } from '../observability/jobs.js';
import { recordHandled } from '../observability/spans.js';
import {
  Dispatched,
  DISPATCH_OPERATION,
  NotificationDispatcher,
} from './notification-dispatcher.js';

/** 몇 밀리초마다 보는가 */
export const DISPATCH_INTERVAL_MS = 5000;

/** 한 바퀴에 처리한 수. 보낸 것, 다시 보낼 것, 받지 않은 것, 예외가 난 것, 오래되어 지운 것을 모두 센다. */
export function handledOf(dispatched: Dispatched): number {
  return Object.values(dispatched).reduce((sum, count) => sum + count, 0);
}

@Injectable()
export class NotificationDispatchRunner
  implements OnApplicationBootstrap, OnModuleDestroy
{
  private readonly logger = new Logger(NotificationDispatchRunner.name);
  private timer: NodeJS.Timeout | undefined;
  private running = false;

  constructor(private readonly dispatcher: NotificationDispatcher) {}

  /** 앱이 뜨면 간격마다 돌기 시작한다. */
  onApplicationBootstrap(): void {
    this.timer = setInterval(() => void this.runOnce(), DISPATCH_INTERVAL_MS);
    this.timer.unref();
  }

  /** 앱이 닫힐 때 멈춘다. */
  onModuleDestroy(): void {
    clearInterval(this.timer);
    this.timer = undefined;
  }

  /**
   * 한 바퀴를 돈다. 앞 바퀴가 돌고 있으면 건너뛴다. 통째로 실패해도(DB 가 없다) 오류로 남기고 다음 바퀴에 다시 한다.
   */
  async runOnce(): Promise<void> {
    if (this.running) {
      return;
    }
    this.running = true;
    try {
      await runAsJob(DISPATCH_OPERATION, () => this.dispatchRound());
    } catch {
      // 실패는 dispatchRound 가 job_id 를 붙여 남겼다. 타이머는 멈추지 않는다
    } finally {
      this.running = false;
    }
  }

  /** 작업 안의 한 바퀴. 처리한 수를 span 에 싣는다. 통째로 실패하면 오류로 남기고 그대로 올린다(span 이 실패로 남는다). */
  async dispatchRound(): Promise<void> {
    try {
      recordHandled(handledOf(await this.dispatcher.tick()));
    } catch (error) {
      this.logger.error(
        {
          message: '알림 보내기가 한 바퀴를 돌지 못했습니다',
          operation: DISPATCH_OPERATION,
          result: 'server_error',
          error_code: 'job.failed',
          error_type:
            error instanceof Error ? error.constructor.name : typeof error,
        },
        error instanceof Error ? error.stack : undefined,
      );
      throw error;
    }
  }
}
