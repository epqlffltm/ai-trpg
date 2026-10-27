// web/apps/web/src/pages/story/storyTurnProblem.ts
// story 의 답을 시작하기 전에 거절된 까닭을 화면의 한 줄과 할 일로. 순수한 함수다. 까닭은 api/story.ts 의 머리말을 본다.
// chat 과 같은 거절(크레딧, 모델, 다른 답을 쓰는 중, 503)은 chat 의 것을 그대로 쓴다. story 에만 있는 것을 먼저 본다.
// 행동을 할 수 없는 까닭(422)은 아무것도 저장하지 않았다. 상태가 화면과 어긋났을 수 있어(다른 가지, 다른 탭) 세션을 다시 읽는다.

import { ApiError } from '../../api/errors';
import { describeChangeProblem, describeTurnProblem, type TurnProblem } from '../chat/conversation/turnProblem';

const STORY_REFUSALS: Record<string, string> = {
  session_ended: '끝난 이야기입니다. 엔딩을 봤고 이 세계관은 후일담이 없습니다.',
  message_not_found: '그 말을 찾지 못했습니다. 화면을 새로 읽습니다.',
  not_regenerable: '다시 쓸 수 없는 말입니다.',
  cannot_move: '지금 있는 곳에서 바로 갈 수 없는 곳입니다.',
  no_choice: '고를 선택지가 없습니다. 화면을 새로 읽습니다.',
  over: '이야기가 끝나 더 할 수 없습니다.',
  not_in_scene: '그 인물은 지금 장면에 없습니다.',
  not_confessable: '그 인물에게는 고백할 수 없습니다.',
  cooling_down: '아직 다시 고백할 수 없습니다. 며칠 지난 뒤에 해 보세요.',
  not_held: '가지고 있지 않은 물건입니다.',
  not_editable: '고칠 수 없는 말입니다. 행동 말은 엔진의 결과라 고치지 않습니다.',
};

export function describeStoryTurnProblem(error: unknown): TurnProblem {
  const text = error instanceof ApiError && error.code ? STORY_REFUSALS[error.code] : undefined;
  if (text) return { text, charge: false, chooseModel: false, reload: true };
  return describeTurnProblem(error);
}

/** 세션을 시작하지 못한 까닭 */
export function describeStartProblem(error: unknown): string {
  if (!(error instanceof ApiError)) return '서버에 닿지 못했습니다. 연결을 확인하고 다시 시도하세요.';
  if (error.code === 'adult_content_required') return '성인 등급의 세계관입니다. 본인인증으로 성인임을 확인한 뒤에 시작합니다.';
  if (error.code === 'world_not_found' || error.status === 404) return '시작할 수 없는 세계관입니다. 게시한 판이 없거나 볼 수 없습니다.';
  if (error.code === 'asset_unavailable') return `세계관을 가져오지 못했습니다.${error.retryAfter ? ` ${error.retryAfter}초 뒤에` : ' 잠시 뒤에'} 다시 눌러 주세요.`;
  if (error.status === 503) return '지금은 시작할 수 없습니다. 잠시 뒤에 다시 시도하세요.';
  return '시작하지 못했습니다. 잠시 뒤에 다시 시도하세요.';
}

/** 답 고치기(PATCH)와 대안 고르기의 실패. 조각의 수가 다르면 다시 읽어 맞춘다 */
export function describeStoryEditProblem(error: unknown): string {
  if (error instanceof ApiError && error.code === 'segments_mismatch') return '조각의 수가 바뀌었습니다. 화면을 새로 읽은 뒤 다시 고쳐 주세요.';
  if (error instanceof ApiError && error.code === 'not_editable') return '고칠 수 없는 말입니다. 답만 그 자리에서 고칩니다.';
  return describeChangeProblem(error);
}
