// web/apps/web/src/pages/notifications/notificationProblem.ts
// 알림함을 읽거나 바꾸지 못한 까닭을 화면의 한 줄로. 순수한 함수다.
// 알림 서버의 503 은 공개키를 구할 수 없을 때다(Retry-After). 로그아웃시키지 않는다. 401 은 http.ts 와 RequireSession 이 맡는다.

import { ApiError, NetworkError } from '../../api/errors';

export function notificationProblemText(error: unknown): string {
  if (error instanceof NetworkError) return '서버에 닿지 못했습니다. 연결을 확인하고 다시 시도하세요.';
  if (error instanceof ApiError && error.status === 503) {
    const after = error.retryAfter ? ` ${error.retryAfter}초 뒤에` : ' 잠시 뒤에';
    return `알림 서버가 지금 답하지 못합니다.${after} 다시 시도하세요.`;
  }
  if (error instanceof ApiError && error.status === 422) return '끌 수 없는 알림입니다. 목록을 다시 읽습니다.';
  return '알림을 처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';
}
