// web/apps/web/src/pages/trpg/studio/rulebooks/rulebookProblem.ts
// 룰북 화면(B9)의 실패를 보일 것으로 바꾼다. 순수한 함수다.
//
// 게임 서버의 답(trpg-server/app/assets/routing.py):
//   - 404: 그런 룰북이 없다. 남의 것도 404 다
//   - 409(지울 때): 이 룰북을 쓰는 시나리오가 있다. 본문의 used_by[{id, title}]
//   - 422: 받지 않는 값. 화면이 먼저 검사하므로(rulebookHints) 서버의 규칙이 바뀌었을 때만 온다

import { ApiError } from '../../../../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../../../../auth/problem';

const FAILED = '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';
const MISSING = '룰북을 찾을 수 없습니다. 지워졌을 수 있습니다.';

/** 만들기와 고치기 */
export function describeSaveProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 404) return { message: MISSING };
  if (error.status === 422) return { message: '서버가 받지 않는 값이 있습니다. 칸을 다시 확인해 주세요.' };
  return unknownProblem(error, FAILED);
}

/** 지우기. 쓰는 시나리오가 있으면 그 제목들을 함께 적는다 */
export function describeDeleteProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 404) return { message: MISSING };
  if (error.status === 409) {
    const titles = usedByTitles(error.body);
    const list = titles.length > 0 ? ` 쓰는 시나리오: ${titles.join(', ')}.` : '';
    return { message: `이 룰북을 쓰는 시나리오가 있어 지울 수 없습니다. 시나리오에서 룰북을 뗀 뒤 다시 지우세요.${list}` };
  }
  return unknownProblem(error, FAILED);
}

/** 409 의 used_by 에서 제목들. 모양이 다르면 빈 목록 */
export function usedByTitles(body: Record<string, unknown>): string[] {
  const usedBy = body.used_by;
  if (!Array.isArray(usedBy)) return [];
  return usedBy.flatMap((one: unknown) => {
    const title = one !== null && typeof one === 'object' ? (one as Record<string, unknown>).title : undefined;
    return typeof title === 'string' ? [title] : [];
  });
}
