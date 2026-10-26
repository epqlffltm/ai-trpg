// web/apps/web/src/pages/operator/sanctionProblem.ts
// 게임 서버의 제재가 되지 않은 까닭을 보일 문장으로. 순수한 함수다. 까닭은 api/gameOperator.ts 의 머리말을 본다.
// 409 의 까닭(not_published, already_banned, not_banned) 말고는 신고 처리와 같다(moderationProblem.ts).

import { ApiError } from '../../api/errors';
import type { FormProblem } from '../../auth/problem';
import { describeModerationProblem } from './moderationProblem';

const CONFLICTS: Record<string, string> = {
  not_published: '공개 중인 판이 없어 제재할 것이 없습니다. 이미 내려갔을 수 있습니다.',
  already_banned: '이미 공개 금지 중인 사람입니다.',
  not_banned: '공개 금지 중이 아닌 사람입니다.',
};

export function describeSanctionProblem(error: unknown): FormProblem {
  if (error instanceof ApiError && error.status === 409) {
    return { message: (error.code ? CONFLICTS[error.code] : undefined) ?? '지금 상태에서는 할 수 없습니다.' };
  }
  return describeModerationProblem(error);
}
