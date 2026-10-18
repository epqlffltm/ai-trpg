// board-server/src/notifications/notification-client.ts

/**
 * 알림 서버를 부르는 것. 요청마다 서명하고(signing.ts), 답을 결과로 바꾼다.
 *
 * 주소와 답의 뜻은 알림 서버가 정했다(notification-server/README.md 의 "알림 넣기").
 *
 * | 답 | 결과 |
 * | --- | --- |
 * | 201(새로 넣었다), 200(이미 있다) | 보냈다(delivered) |
 * | 401, 408, 429, 5xx, 닿지 못함, 시간 초과 | 다시 보낼 일(unavailable) |
 * | 409(같은 열쇠로 다른 알림), 413, 422, 그 밖의 4xx·3xx | 받지 않았다(rejected). 버그다 |
 *
 * 401 은 서명이 거절된 것이다. 두 서버의 비밀이 다르거나 시계가 5분 넘게 어긋났다. 설정을 고치면 낫는 일이라 다시 보낸다.
 * 다른 주소로 가라는 답(3xx)은 따라가지 않는다. 서명한 요청이 우리가 고르지 않은 곳으로 가면 안 된다.
 */

import { OutgoingNotification } from './outgoing-notification.entity.js';
import { SIGNATURE_HEADER, sign } from './signing.js';

/** 게시판 서버가 알림을 넣는 주소. 주소에 넣는 서버의 이름(board)이 들어간다 */
export const PUT_PATH = '/api/v1/notification/service/board/notifications';
/** 알림 서버의 답을 기다리는 시간(밀리초) */
export const SEND_TIMEOUT_MS = 5000;
/** 다시 보내면 될 수 있는 답. 시간 초과(408), 너무 많음(429) */
const RETRYABLE_STATUSES = new Set([408, 429]);

/** 알림 하나를 보낸 결과 */
export type Delivery = 'delivered' | 'unavailable' | 'rejected';

/** 보낸 결과와 그 까닭의 이름(보내지 못했을 때). 까닭은 발송함과 로그에 남는다 */
export interface Sent {
  delivery: Delivery;
  reason?: string;
}

/** 알림을 보내는 것의 모양. 테스트는 가짜를 꽂는다. 예외를 내지 않고 결과로 돌려준다 */
export interface NotificationSender {
  send(notification: OutgoingNotification): Promise<Sent>;
}

/** 보낼 본문. 이 글자에 서명하고 이 글자를 보낸다. 알림 서버가 모르는 칸은 넣지 않는다(422). */
export function encode(notification: OutgoingNotification): string {
  return JSON.stringify({
    source_key: notification.sourceKey,
    user_id: notification.userId,
    kind: notification.kind,
    payload: notification.payload,
  });
}

/** 알림 서버의 답을 결과로 바꾼다. 위의 표다. */
export function resultOf(status: number): Sent {
  if (status === 200 || status === 201) {
    return { delivery: 'delivered' };
  }
  if (status === 401) {
    return { delivery: 'unavailable', reason: 'unauthorized' };
  }
  if (status >= 500 || RETRYABLE_STATUSES.has(status)) {
    return { delivery: 'unavailable', reason: `status_${status}` };
  }
  return { delivery: 'rejected', reason: `status_${status}` };
}

/** 답을 받지 못한 까닭의 이름. 시간이 다 됐으면 timeout, 그 밖에는 unreachable 이다. 오류의 글(주소가 든다)은 싣지 않는다. */
export function transportReason(error: unknown): string {
  const name = error instanceof Error ? error.name : '';
  return name === 'TimeoutError' || name === 'AbortError'
    ? 'timeout'
    : 'unreachable';
}

/** 알림 서버를 실제로 부르는 것. */
export class HttpNotificationSender implements NotificationSender {
  constructor(
    private readonly baseUrl: string,
    private readonly secret: string,
    private readonly now: () => Date = () => new Date(),
  ) {}

  /** 알림 하나를 보낸다. 답을 받지 못하면 다시 보낼 일이다. */
  async send(notification: OutgoingNotification): Promise<Sent> {
    const body = encode(notification);
    try {
      const response = await fetch(this.urlOf(), {
        method: 'POST',
        headers: this.headersFor(body),
        body,
        redirect: 'manual',
        signal: AbortSignal.timeout(SEND_TIMEOUT_MS),
      });
      return resultOf(response.status);
    } catch (error) {
      return { delivery: 'unavailable', reason: transportReason(error) };
    }
  }

  /** 보낼 주소. 끝의 / 는 떼고 붙인다. */
  urlOf(): string {
    return this.baseUrl.replace(/\/+$/, '') + PUT_PATH;
  }

  /** 보낼 머리말. 서명이다. */
  headersFor(body: string): Record<string, string> {
    const sentAt = Math.floor(this.now().getTime() / 1000);
    return {
      'Content-Type': 'application/json',
      [SIGNATURE_HEADER]: sign(this.secret, sentAt, 'POST', PUT_PATH, body),
    };
  }
}
