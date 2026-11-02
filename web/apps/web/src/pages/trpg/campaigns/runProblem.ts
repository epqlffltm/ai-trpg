// web/apps/web/src/pages/trpg/campaigns/runProblem.ts
// 캠페인의 플레이를 시작하고, 다음 편을 열고, 들어가는 일의 실패를 보일 것으로 바꾼다. 순수한 함수다.
// 테이블을 열고 앉는 실패는 테이블 만들기와 들어가기의 글을 쓴다(tables/tableProblem.ts).
//
// 플레이에만 있는 답(trpg-server/app/campaigns/router.py):
//   - 시작: 404 캠페인이 없거나 게시한 판이 없다
//   - 다음 편: 409 reason episode_not_ended(앞 편이 끝나지 않았다), run_ended(마쳤다). 403 방장이 아니다
//   - 들어가기: 404 그 플레이의 사람이 아니다. 409 not_recruiting 이면 다음 편이 이미 시작했다

import { ApiError } from '../../../api/errors';
import { commonProblem, type FormProblem } from '../../../auth/problem';
import { describeCreateProblem, describeJoinProblem, type TableProblem } from '../tables/tableProblem';

/** 플레이 시작 */
export function describeStartProblem(error: unknown): FormProblem {
  if (commonProblem(error) || !(error instanceof ApiError)) return describeCreateProblem(error);
  if (error.status === 404) return { message: '게시한 판이 없거나 캠페인을 찾을 수 없습니다. 캠페인을 먼저 게시해 주세요.' };
  return describeCreateProblem(error);
}

/** 다음 편 열기 */
export function describeOpenNextProblem(error: unknown): FormProblem {
  if (commonProblem(error) || !(error instanceof ApiError)) return describeCreateProblem(error);
  if (error.status === 409 && error.code === 'episode_not_ended') return { message: '이 편이 아직 끝나지 않았습니다.' };
  if (error.status === 409 && error.code === 'run_ended') return { message: '캠페인을 이미 마쳤습니다.' };
  if (error.status === 403 && error.code === undefined) return { message: '방장만 다음 편을 열 수 있습니다.' };
  if (error.status === 404) return { message: '플레이를 찾을 수 없습니다.' };
  return describeCreateProblem(error);
}

/** 다음 편에 들어가기. 이미 앉아 있으면 seated 다(그 테이블로 간다) */
export function describeJoinNextProblem(error: unknown): TableProblem {
  if (error instanceof ApiError && error.status === 404) return { message: '이 플레이의 사람만 들어갈 수 있습니다.' };
  if (error instanceof ApiError && error.status === 409 && error.code === 'not_recruiting') {
    return { message: '다음 편이 이미 시작해 들어갈 수 없습니다.' };
  }
  return describeJoinProblem(error);
}
