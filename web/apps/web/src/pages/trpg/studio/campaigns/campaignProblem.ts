// web/apps/web/src/pages/trpg/studio/campaigns/campaignProblem.ts
// 캠페인의 편 저장과 게시의 실패를 보일 것으로 바꾼다. 순수한 함수다. 재료와 같은 실패(404 …)는 재료의 글을 쓴다.
//
// 캠페인에만 있는 답(trpg-server/app/assets/campaigns/router.py, app/assets/routing.py):
//   - 422 {detail}(편 저장): 지웠거나 남의 시나리오를 편에 넣었다. 칸의 오류(errors)가 아니다
//   - 409 {problems}(게시): 게시할 조건을 갖추지 못했다. 무엇인지는 게시 점검이 보인다
//   - 403 code adult_content_required(게시): 성인용 편이 있는데 성인 확인을 하지 않았다

import { ApiError, isInputError } from '../../../../api/errors';
import { commonProblem, type FormProblem } from '../../../../auth/problem';
import { describeSaveProblem } from '../studioProblem';

const SCENARIO_GONE = '지웠거나 쓸 수 없는 시나리오가 편에 있습니다. 화면을 새로 불러온 뒤 그 편을 빼 주세요.';
const NOT_READY = '게시할 조건을 갖추지 못했습니다. 게시 점검의 문제를 고친 뒤 다시 게시하세요.';
const ADULT_ONLY = '성인용 편이 있어 본인인증으로 성인 확인을 한 사람만 게시할 수 있습니다.';

/** 편의 저장 */
export function describeEpisodesProblem(error: unknown): FormProblem {
  if (commonProblem(error) || !(error instanceof ApiError)) return describeSaveProblem(error, 'campaigns');
  if (error.status === 422 && !isInputError(error)) return { message: SCENARIO_GONE };
  return describeSaveProblem(error, 'campaigns');
}

/** 게시 */
export function describeCampaignPublishProblem(error: unknown): FormProblem {
  if (error instanceof ApiError && error.status === 409 && Array.isArray(error.body.problems)) return { message: NOT_READY };
  if (error instanceof ApiError && error.status === 403 && error.code === 'adult_content_required') return { message: ADULT_ONLY };
  return describeSaveProblem(error, 'campaigns');
}
