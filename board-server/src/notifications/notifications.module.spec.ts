// board-server/src/notifications/notifications.module.spec.ts

/**
 * 설정으로 알림 서버를 부르는 것을 만드는 것(notifications.module.ts 의 senderFrom)을 검증한다.
 */

import { ConfigService } from '@nestjs/config';
import { Environment } from '../config/environment.js';
import { HttpNotificationSender } from './notification-client.js';
import { senderFrom } from './notifications.module.js';

/** 정해 둔 값을 내주는 설정. */
function config(
  values: Partial<Environment>,
): ConfigService<Environment, true> {
  return {
    get: (name: keyof Environment) => values[name],
  } as unknown as ConfigService<Environment, true>;
}

describe('senderFrom', () => {
  it('주소가 없으면 부르지 않는다', () => {
    expect(
      senderFrom(config({ NOTIFICATION_URL: '', NOTIFICATION_SECRET: '' })),
    ).toBeNull();
  });

  it('주소가 있으면 그 주소로 서명해 부른다', () => {
    const sender = senderFrom(
      config({
        NOTIFICATION_URL: 'http://notification:8004/',
        NOTIFICATION_SECRET: 'board-notification-test-secret-of-32',
      }),
    );

    expect(sender).toBeInstanceOf(HttpNotificationSender);
    expect((sender as HttpNotificationSender).urlOf()).toBe(
      'http://notification:8004/api/v1/notification/service/board/notifications',
    );
  });
});
