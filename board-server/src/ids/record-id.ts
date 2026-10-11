// board-server/src/ids/record-id.ts

/**
 * 순번으로 매긴 번호(글 번호, 댓글 번호)의 모양. 순수한 함수다.
 *
 * 번호는 1 이상의 정수다. 코드와 응답에서는 글자로 다룬다. JavaScript 의 숫자는 큰 정수를 정확히 담지 못한다.
 * 주소나 본문으로 받은 번호는 DB 에 묻기 전에 이 모양인지 먼저 본다. 숫자가 아닌 값을 번호 칸에 물으면
 * DB 가 오류를 낸다.
 */

/** 번호의 모양. 0 으로 시작하지 않는 숫자, 18자리까지. DB 의 bigint 에 들어가는 크기다 */
export const RECORD_ID = /^[1-9]\d{0,17}$/;

/** 값이 번호의 모양인 글자인가. */
export function isRecordId(value: unknown): value is string {
  return typeof value === 'string' && RECORD_ID.test(value);
}
