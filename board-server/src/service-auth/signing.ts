// board-server/src/service-auth/signing.ts

/**
 * 우리 서버끼리의 요청에 서명하고, 받은 요청의 서명을 확인한다. 모양은 결제 서버가 정했고 다른 서버도 같다
 * (billing-server/internal/serviceauth, shared/server-core 의 server_core/service_auth/signing.py).
 *
 *     X-Service-Signature: t=<보낸 시각(초)>,v1=<HMAC-SHA256(비밀, "<시각>.<메서드>\n<경로>\n<본문>") 의 16진수>
 *
 * 본문은 보내는 바이트 그대로에 서명한다. JSON 을 한 번 만들어 서명하고 그것을 보낸다.
 * 서명하는 것: 알림 서버에 보내는 알림(notifications/). 확인하는 것: 인증 서버가 알리는 탈퇴(withdrawals/).
 */

import { createHmac, timingSafeEqual } from 'node:crypto';

/** 서명을 싣는 머리말 */
export const SIGNATURE_HEADER = 'X-Service-Signature';

/** 받는 서명의 시각이 지금과 이만큼(초)까지 어긋나도 받는다. 다른 서버와 같다 */
export const TOLERANCE_SECONDS = 300;

/** 비밀의 가장 짧은 길이. 이보다 짧은 비밀로는 하나도 받지 않는다. 다른 서버와 같다 */
export const MIN_SECRET_LENGTH = 32;

/** 머리말의 모양. 시각은 정수, 서명은 16진수 64자다 */
const HEADER = /^t=(?<sentAt>-?\d{1,19}),v1=(?<signature>[0-9a-f]{64})$/;

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

/** 받은 바이트(body)로 만든 서명의 16진수. 받은 본문을 글자로 바꾸지 않는다. 바꾸면 깨진 바이트가 다른 글자가 된다. */
function digestOfBytes(
  secret: string,
  sentAt: number,
  method: string,
  path: string,
  body: Buffer,
): string {
  return createHmac('sha256', secret)
    .update(`${sentAt}.${method}\n${path}\n`, 'utf8')
    .update(body)
    .digest('hex');
}

/**
 * 머리말의 서명이 이 요청(메서드, 경로, 본문)의 것이고 방금 만든 것인가.
 *
 * 이유를 나누지 않고 참/거짓만 답한다. 무엇이 틀렸는지 알려 주면 서명을 꾸며 내는 쪽에 도움이 된다.
 * 비밀이 비었거나 짧으면 하나도 받지 않는다. nowSeconds 는 지금 시각(초)이다.
 */
export function isValidSignature(
  secret: string,
  header: string | undefined,
  method: string,
  path: string,
  body: Buffer,
  nowSeconds: number,
): boolean {
  if (secret.length < MIN_SECRET_LENGTH || header === undefined) {
    return false;
  }
  const parts = HEADER.exec(header)?.groups;
  if (parts === undefined) {
    return false;
  }
  const sentAt = Number(parts.sentAt);
  const expected = Buffer.from(
    digestOfBytes(secret, sentAt, method, path, body),
  );
  // 두 서명을 견줄 때 걸리는 시간이 어디서 틀렸는지에 따라 달라지지 않게 한다. 길이는 모양에서 이미 같다
  if (!timingSafeEqual(Buffer.from(parts.signature), expected)) {
    return false;
  }
  return Math.abs(nowSeconds - sentAt) <= TOLERANCE_SECONDS;
}
