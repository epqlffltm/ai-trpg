// web/apps/web/src/pages/trpg/room/transcript/transcriptProblem.ts
// 기록을 받지 못한 까닭을 화면의 한 줄로. 순수한 함수다. 까닭은 api/transcripts.ts 의 머리말을 본다.

import { ApiError, NetworkError } from '../../../../api/errors';

export function transcriptProblemText(error: unknown): string {
  if (error instanceof NetworkError) return '서버에 닿지 못했습니다. 연결을 확인하고 다시 받아 주세요.';
  if (!(error instanceof ApiError)) return '기록을 받지 못했습니다. 다시 받아 주세요.';
  if (error.status === 429) return `기록은 10분에 10번까지 받습니다. ${error.retryAfter ?? 60}초 뒤에 다시 받아 주세요.`;
  if (error.status === 404) return '이 테이블에 앉아 있지 않아 기록을 받을 수 없습니다.';
  return '기록을 받지 못했습니다. 잠시 뒤에 다시 받아 주세요.';
}
