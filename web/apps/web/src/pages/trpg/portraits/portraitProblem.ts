// web/apps/web/src/pages/trpg/portraits/portraitProblem.ts
// 캐릭터 그림(#983)의 올리기와 지우기의 실패를 글로 바꾼다. 순수한 함수다.
// 올리기의 형식·크기·열 수 없음은 asset 의 그림 올리기와 같은 글을 쓴다(components/imageFile.ts).

import { ApiError } from '../../../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../../../auth/problem';
import { describeUploadProblem } from '../../../components/imageFile';

/** 한 사람이 올릴 수 있는 그림의 수. 서버의 PORTRAIT_MAX_PER_OWNER */
export const PORTRAIT_MAX = 100;

export type PortraitUser = { id: string; title: string };

/** 올리기 */
export function describePortraitUploadProblem(error: unknown): FormProblem {
  if (error instanceof ApiError && error.status === 409 && error.code === 'portrait_limit') {
    return { message: `캐릭터 그림은 ${PORTRAIT_MAX}장까지 올릴 수 있습니다. 쓰지 않는 그림을 지운 뒤 올려 주세요.` };
  }
  if (error instanceof ApiError && error.status === 503) return { message: '지금은 그림을 올릴 수 없습니다. 잠시 뒤에 다시 해 주세요.' };
  return describeUploadProblem(error);
}

/** 지우기를 막은 시나리오들. portrait_in_use 가 아니면 빈 목록 */
export function portraitUsers(error: unknown): PortraitUser[] {
  if (!(error instanceof ApiError) || error.code !== 'portrait_in_use' || !Array.isArray(error.body.scenarios)) return [];
  return (error.body.scenarios as PortraitUser[]).filter((scenario) => typeof scenario.id === 'string');
}

/** 지우기 */
export function describePortraitDeleteProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: '지우지 못했습니다.' };
  if (error.status === 409 && error.code === 'portrait_in_use') {
    return { message: '이 그림을 쓰는 시나리오가 있습니다. 게시한 판에 남아 있으면 초안에서 떼도 지울 수 없습니다.' };
  }
  if (error.status === 404) return { message: '이미 지웠거나 찾을 수 없는 그림입니다.' };
  return unknownProblem(error, '지우지 못했습니다.');
}
