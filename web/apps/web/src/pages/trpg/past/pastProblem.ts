// web/apps/web/src/pages/trpg/past/pastProblem.ts
// 떠난 테이블을 읽지 못한 까닭을 화면의 한 줄로. 순수한 함수다.
// 404 는 떠난 적이 없는 테이블이다(지금 앉아 있는 테이블도 여기서는 404 다. 앉은 사람의 길로 읽는다).

import { ApiError, NetworkError } from '../../../api/errors';

export function pastProblemText(error: unknown): string {
  if (error instanceof NetworkError) return '서버에 닿지 못했습니다. 연결을 확인하고 다시 시도하세요.';
  if (error instanceof ApiError && error.status === 404) return '떠난 기록이 없는 테이블입니다. 지금 앉아 있는 테이블이면 테이블 방에서 읽습니다.';
  return '불러오지 못했습니다. 잠시 뒤에 다시 시도하세요.';
}
