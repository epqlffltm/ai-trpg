// board-server/src/notifications/notifications.module.ts

/**
 * 사용자의 알림함(알림 서버)에 알림을 넣는 모듈(#385).
 *
 * 발송함(outgoing_notifications)의 엔티티를 등록하고, 알림 서버를 부르는 것과 보내는 작업을 만든다.
 * 발송함에 적는 것은 그 일을 하는 모듈이 제 트랜잭션에서 한다(outbox.ts 의 queueNotices). 이 모듈을 가져올 필요가 없다.
 *
 * 알림 서버의 주소(NOTIFICATION_URL)가 없으면 부르는 것이 null 이다. 그때 알림은 적히기만 한다.
 */

import { Module } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Environment } from '../config/environment.js';
import {
  HttpNotificationSender,
  NotificationSender,
} from './notification-client.js';
import {
  NOTIFICATION_SENDER,
  NotificationDispatcher,
} from './notification-dispatcher.js';
import { NotificationDispatchRunner } from './notification-dispatcher.runner.js';
import { OutgoingNotification } from './outgoing-notification.entity.js';

/** 설정으로 알림 서버를 부르는 것을 만든다. 주소가 없으면 null 이다. */
export function senderFrom(
  config: ConfigService<Environment, true>,
): NotificationSender | null {
  const url = config.get('NOTIFICATION_URL', { infer: true });
  if (url === '') {
    return null;
  }
  return new HttpNotificationSender(
    url,
    config.get('NOTIFICATION_SECRET', { infer: true }),
  );
}

@Module({
  imports: [TypeOrmModule.forFeature([OutgoingNotification])],
  providers: [
    {
      provide: NOTIFICATION_SENDER,
      inject: [ConfigService],
      useFactory: senderFrom,
    },
    NotificationDispatcher,
    NotificationDispatchRunner,
  ],
  exports: [NotificationDispatcher],
})
export class NotificationsModule {}
