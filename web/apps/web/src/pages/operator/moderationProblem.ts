// web/apps/web/src/pages/operator/moderationProblem.ts
// 신고 처리(E4)의 실패를 보일 것으로 바꾼다. 순수한 함수다.
//
// 서버의 답(asset-server/app/operators/, chat-server/app/operators/):
//   - 404: 그런 캐릭터나 신고가 없다. 운영자가 아니어도 404 다(주소가 있다는 것을 알리지 않는다)
//   - 409 already_handled: 이미 처리한 대화 속 답의 신고다(다른 운영자가 먼저 했다)
//   - 422: 사유가 비었거나 너무 길다. 화면이 먼저 검사하므로 서버의 규칙이 바뀌었을 때만 온다

import { ApiError } from '../../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../../auth/problem';

const FAILED = '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';

export type ModerationProblem = FormProblem & {
  /** 목록을 다시 읽어야 한다(이미 처리했거나 없어졌다) */
  refresh?: boolean;
};

export function describeModerationProblem(error: unknown): ModerationProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 404) return { message: '찾을 수 없습니다. 지워졌거나 운영자 권한이 없습니다.', refresh: true };
  if (error.status === 409) return { message: '이미 처리한 신고입니다. 목록을 다시 읽습니다.', refresh: true };
  if (error.status === 422) return { message: '서버가 받지 않는 값이 있습니다. 사유를 다시 확인해 주세요.' };
  return unknownProblem(error, FAILED);
}
