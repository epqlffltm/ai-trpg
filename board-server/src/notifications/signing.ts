// board-server/src/notifications/signing.ts

/**
 * 알림 서버에 보내는 요청에 서명한다. 모양은 결제 서버가 정했고 알림 서버도 같다(billing-server/internal/serviceauth).
 *
 *     X-Service-Signature: t=<보낸 시각(초)>,v1=<HMAC-SHA256(비밀, "<시각>.<메서드>\n<경로>\n<본문>") 의 16진수>
 *
 * 본문은 보내는 바이트 그대로에 서명한다. JSON 을 한 번 만들어 서명하고 그것을 보낸다.
 */

import { createHmac } from 'node:crypto';

/** 서명을 싣는 머리말 */
export const SIGNATURE_HEADER = 'X-Service-Signature';

/** 서명하는 글자. 보낸 시각과 요청이다. 메서드와 경로에는 줄바꿈이 없어서 세 부분이 섞이지 않는다. */
export function signedContent(
  sentAt: number,
  method: string,
  path: string,
  body: string,
): string {
  return `${sentAt}.${method}\n${path}\n${body}`;
}

/** 요청에 서명해 머리말에 실을 글자를 만든다. path 는 호스트를 뺀 경로다. sentAt 은 초다. */
export function sign(
  secret: string,
  sentAt: number,
  method: string,
  path: string,
  body: string,
): string {
  const digest = createHmac('sha256', secret)
    .update(signedContent(sentAt, method, path, body), 'utf8')
    .digest('hex');
  return `t=${sentAt},v1=${digest}`;
}
