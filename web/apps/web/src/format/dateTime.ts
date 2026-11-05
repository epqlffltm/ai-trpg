// web/apps/web/src/format/dateTime.ts
// 서버가 준 시각(ISO 8601)을 화면의 글로 바꾼다. 보는 사람의 시간대로 보인다.

const DATE_TIME = new Intl.DateTimeFormat('ko-KR', { dateStyle: 'long', timeStyle: 'short' });
const DATE = new Intl.DateTimeFormat('ko-KR', { dateStyle: 'long' });
const TIME = new Intl.DateTimeFormat('ko-KR', { timeStyle: 'short' });

/** "2026년 10월 29일 오후 3:00" 꼴. 읽지 못하는 값이면 받은 그대로 */
export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : DATE_TIME.format(date);
}

/** "2026년 10월 29일" 꼴. 읽지 못하는 값이면 받은 그대로 */
export function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : DATE.format(date);
}

/** "오후 9:30" 꼴(시각만). 읽지 못하는 값이면 받은 그대로 */
export function formatTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : TIME.format(date);
}
