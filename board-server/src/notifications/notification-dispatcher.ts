// board-server/src/notifications/notification-dispatcher.ts

/**
 * 발송함의 알림을 알림 서버에 보낸다. 한 바퀴(tick)에 두 가지를 한다. 바퀴를 돌리는 것은 runner 다.
 *
 *   1. 오래(STALE_AFTER_MS, 7일) 보내지 못한 알림을 지운다. 알림 서버가 오래 죽어 있었거나 주소를 비워 둔 동안 쌓인 것이다
 *   2. 보낼 차례가 된 알림(DISPATCH_BATCH, 50 개까지)을 하나씩 보내고 결과를 적는다
 *      - 보냈다: 줄을 지운다
 *      - 다시 보낼 일: 기다리는 시간을 늘려 다시 보낸다(10초에서 두 배씩 1시간까지)
 *      - 받지 않았다: 실패로 적고 다시 보내지 않는다. 버그라 오류로 남긴다
 *
 * 알림 서버를 부르는 것(sender)이 없으면(NOTIFICATION_URL 을 비웠다) 1 만 한다. 알림은 적히기만 한다.
 *
 * 서버가 여럿이면 모두 같은 일을 한다. 같은 알림을 둘이 보내도 알림 서버는 열쇠로 한 줄만 둔다.
 * 결과는 "아직 기다리는 줄일 때만" 적는다. 한 서버가 지운 줄을 다른 서버가 되살리지 않는다.
 * 게임 서버의 것(game-server/app/notifications/dispatcher.py)과 같은 규칙이다.
 */

import { Inject, Injectable, Logger } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Delivery, NotificationSender, Sent } from './notification-client.js';
import { OutgoingNotification } from './outgoing-notification.entity.js';

/** 알림 서버를 부르는 것을 꽂는 자리. 주소가 없으면 null 이다 */
export const NOTIFICATION_SENDER = Symbol('NOTIFICATION_SENDER');

/** 한 바퀴에 보내는 알림의 수. 밀리면 다음 바퀴에 마저 보낸다 */
export const DISPATCH_BATCH = 50;
/** 이보다 오래 보내지 못한 알림은 보내지 않고 지운다 */
export const STALE_AFTER_MS = 7 * 24 * 60 * 60 * 1000;
/** 다시 보내기까지 기다리는 시간. 처음 10초, 한 번 더 못 보낼 때마다 두 배, 1시간까지 */
const RETRY_BASE_MS = 10_000;
const RETRY_MAX_MS = 60 * 60 * 1000;

/** 로그의 operation 과 error_code. 정해진 이름이다(저장소 루트의 docs/observability.md) */
export const DISPATCH_OPERATION = 'notification.send';
export const UNAVAILABLE_ERROR_CODE = 'notification.unavailable';
export const REJECTED_ERROR_CODE = 'notification.rejected';

/** 한 바퀴에 한 일. 보낸 수, 다시 보낼 수, 받지 않은 수, 보내다 예외가 난 수, 오래되어 지운 수 */
export interface Dispatched {
  sent: number;
  retried: number;
  rejected: number;
  failed: number;
  dropped: number;
}

/** attempts 번째로 보내지 못한 뒤에 다시 보내기까지 기다리는 시간(밀리초). */
export function retryDelayMs(attempts: number): number {
  return Math.min(RETRY_BASE_MS * 2 ** Math.max(attempts - 1, 0), RETRY_MAX_MS);
}

/** 한 일이 있었는가. */
export function isBusy(dispatched: Dispatched): boolean {
  return Object.values(dispatched).some((count) => count > 0);
}

/** 알림 하나를 보낸 것을 더한다. null 이면 보내다 예외가 났다. */
export function countDelivery(
  dispatched: Dispatched,
  delivery: Delivery | null,
): Dispatched {
  return {
    ...dispatched,
    sent: dispatched.sent + (delivery === 'delivered' ? 1 : 0),
    retried: dispatched.retried + (delivery === 'unavailable' ? 1 : 0),
    rejected: dispatched.rejected + (delivery === 'rejected' ? 1 : 0),
    failed: dispatched.failed + (delivery === null ? 1 : 0),
  };
}

@Injectable()
export class NotificationDispatcher {
  private readonly logger = new Logger(NotificationDispatcher.name);

  constructor(
    @InjectRepository(OutgoingNotification)
    private readonly outbox: Repository<OutgoingNotification>,
    @Inject(NOTIFICATION_SENDER)
    private readonly sender: NotificationSender | null,
  ) {}

  /** 한 바퀴. 오래된 알림을 지우고, 보낼 곳이 있으면 차례가 된 알림을 보낸다. 끝나면 한 줄을 남긴다. */
  async tick(now: Date = new Date()): Promise<Dispatched> {
    let dispatched: Dispatched = {
      sent: 0,
      retried: 0,
      rejected: 0,
      failed: 0,
      dropped: await this.dropStale(now),
    };
    if (this.sender !== null) {
      for (const notification of await this.due(now)) {
        dispatched = countDelivery(
          dispatched,
          await this.deliverSafely(this.sender, notification, now),
        );
      }
    }
    this.logRound(dispatched);
    return dispatched;
  }

  /** 오래 보내지 못한 알림을 지운다. 지운 수. 받지 않은 것(failed)은 사람이 볼 때까지 남긴다. */
  async dropStale(now: Date): Promise<number> {
    const result = await this.outbox
      .createQueryBuilder()
      .delete()
      .where(`"status" = 'pending' AND "created_at" < :cutoff`, {
        cutoff: new Date(now.getTime() - STALE_AFTER_MS),
      })
      .execute();
    return result.affected ?? 0;
  }

  /** 보낼 차례가 된 알림들. 먼저 적은 것부터다. 잠그지 않는다. */
  due(now: Date): Promise<OutgoingNotification[]> {
    return this.outbox
      .createQueryBuilder('notification')
      .where(`notification.status = 'pending'`)
      .andWhere(
        '(notification.nextAttemptAt IS NULL OR notification.nextAttemptAt <= :now)',
        { now },
      )
      .orderBy('notification.id', 'ASC')
      .limit(DISPATCH_BATCH)
      .getMany();
  }

  /** 알림 하나를 보내고 결과를 적는다. 예외가 나면 로그에 남기고 null. 한 알림이 실패해도 다른 알림은 보낸다. */
  async deliverSafely(
    sender: NotificationSender,
    notification: OutgoingNotification,
    now: Date,
  ): Promise<Delivery | null> {
    try {
      const sent = await sender.send(notification);
      await this.record(notification, sent, now);
      this.logUnsent(notification, sent);
      return sent.delivery;
    } catch (error) {
      this.logger.error(
        {
          message: '알림을 보내지 못했습니다',
          operation: DISPATCH_OPERATION,
          notification_id: notification.id,
          kind: notification.kind,
          result: 'server_error',
          error_code: 'job.failed',
          error_type:
            error instanceof Error ? error.constructor.name : typeof error,
        },
        error instanceof Error ? error.stack : undefined,
      );
      return null;
    }
  }

  /** 보낸 결과를 발송함에 적는다. 아직 기다리는 줄일 때만 바꾼다. */
  async record(
    notification: OutgoingNotification,
    sent: Sent,
    now: Date,
  ): Promise<void> {
    const pending = { id: notification.id, status: 'pending' as const };
    if (sent.delivery === 'delivered') {
      await this.outbox.delete({ id: notification.id });
    } else if (sent.delivery === 'unavailable') {
      await this.outbox.update(pending, {
        attempts: () => '"attempts" + 1',
        nextAttemptAt: new Date(
          now.getTime() + retryDelayMs(notification.attempts + 1),
        ),
        lastError: sent.reason ?? '',
      });
    } else {
      await this.outbox.update(pending, {
        status: 'failed',
        lastError: sent.reason ?? '',
      });
    }
  }

  /**
   * 보내지 못한 알림을 로그에 남긴다. 받는 사람과 알림의 내용은 남기지 않는다.
   * 다시 보낼 일은 warning, 서명이 거절된 것(401)과 받지 않은 것은 error 다.
   */
  logUnsent(notification: OutgoingNotification, sent: Sent): void {
    if (sent.delivery === 'delivered') {
      return;
    }
    const rejected = sent.delivery === 'rejected';
    const line = {
      message: rejected
        ? '알림 서버가 알림을 받지 않았습니다'
        : '알림을 보내지 못했습니다. 다시 보냅니다',
      operation: DISPATCH_OPERATION,
      notification_id: notification.id,
      kind: notification.kind,
      result: rejected ? 'client_error' : 'server_error',
      error_code: rejected ? REJECTED_ERROR_CODE : UNAVAILABLE_ERROR_CODE,
      reason: sent.reason,
    };
    if (rejected || sent.reason === 'unauthorized') {
      this.logger.error(line);
    } else {
      this.logger.warn(line);
    }
  }

  /** 한 바퀴의 줄. 한 일이 있으면 info, 없으면 debug 다. */
  logRound(dispatched: Dispatched): void {
    const line = {
      message: '알림 보내기가 한 바퀴를 돌았습니다',
      operation: DISPATCH_OPERATION,
      ...dispatched,
      result: 'success',
    };
    if (isBusy(dispatched)) {
      this.logger.log(line);
    } else {
      this.logger.debug(line);
    }
  }
}
