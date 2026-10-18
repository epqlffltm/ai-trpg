// board-server/src/notifications/notification-dispatcher.runner.ts

/**
 * 발송함의 알림을 정해 둔 간격(5초)마다 보낸다. 앱이 뜨면 돌기 시작하고, 닫힐 때 멈춘다.
 *
 * 보내는 일 자체는 NotificationDispatcher 가 한다. 여기는 언제 돌릴지만 정한다.
 * 앞 바퀴가 끝나지 않았으면 다음 바퀴를 건너뛴다. 알림 서버가 느려도 바퀴가 겹쳐 쌓이지 않는다.
 * 타이머는 프로세스를 붙잡지 않는다(unref). 끊긴 세션 목록 받기(auth/session-revocations.refresher.ts)와 같다.
 */

import {
  Injectable,
  Logger,
  OnApplicationBootstrap,
  OnModuleDestroy,
} from '@nestjs/common';
import {
  DISPATCH_OPERATION,
  NotificationDispatcher,
} from './notification-dispatcher.js';

/** 몇 밀리초마다 보는가 */
export const DISPATCH_INTERVAL_MS = 5000;

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
      await this.dispatcher.tick();
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
    } finally {
      this.running = false;
    }
  }
}
