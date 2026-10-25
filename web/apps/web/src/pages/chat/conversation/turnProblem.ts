// web/apps/web/src/pages/chat/conversation/turnProblem.ts
// 답을 시작하기 전에 거절된 까닭(api/chatConversation.ts 의 머리말)을 화면의 한 줄과 할 일로. 순수한 함수다.
// 행동을 할 수 없는 까닭(422)은 아무것도 저장하지 않았다. 상태가 화면과 어긋났을 수 있어(다른 가지, 다른 탭) 대화를 다시 읽는다.

import { ApiError, NetworkError } from '../../../api/errors';

export type TurnProblem = {
  text: string;
  /** 충전(A7)으로 가는 길을 붙인다 */
  charge: boolean;
  /** 모델 고르기를 연다 */
  chooseModel: boolean;
  /** 대화를 다시 읽는다(사람의 말을 저장했거나, 다른 답을 쓰는 중이다) */
  reload: boolean;
};

const ACTION_REFUSALS: Record<string, string> = {
  no_map: '이 캐릭터에는 지도가 없습니다.',
  place_not_found: '그런 장소가 없습니다.',
  already_there: '이미 그곳에 있습니다.',
  not_connected: '지금 있는 곳에서 바로 갈 수 없는 곳입니다.',
  item_not_found: '그런 물건이 없습니다.',
  not_held: '가지고 있지 않은 물건입니다.',
  not_editable: '고칠 수 없는 말입니다.',
};

export function describeTurnProblem(error: unknown): TurnProblem {
  const problem = (text: string, extra: Partial<TurnProblem> = {}): TurnProblem => ({ text, charge: false, chooseModel: false, reload: false, ...extra });
  if (error instanceof NetworkError) return problem('서버에 닿지 못했습니다. 연결을 확인하고 다시 시도하세요.', { reload: true });
  if (!(error instanceof ApiError)) return problem('답을 받지 못했습니다. 잠시 뒤에 다시 시도하세요.', { reload: true });
  const saved = typeof error.body.message_id === 'string';
  const refusal = ACTION_REFUSALS[error.code ?? ''];
  if (error.status === 422 && refusal) return problem(refusal, { reload: true });
  const tail = saved ? ' 보낸 말은 남았습니다. 나중에 다시 생성하면 답을 받습니다.' : '';
  switch (error.code) {
    case 'credit_short':
      return problem(`크레딧이 모자랍니다.${tail}`, { charge: true, reload: saved });
    case 'gold_required':
      return problem(`이 모델은 골드로만 냅니다. 골드가 모자랍니다.${tail}`, { charge: true, reload: saved });
    case 'model_required':
      return problem('먼저 대화에 쓸 모델을 골라 주세요.', { chooseModel: true });
    case 'model_unavailable':
      return problem(`지금 이 모델을 쓸 수 없습니다. 다른 모델을 골라 주세요.${tail}`, { chooseModel: true, reload: true });
    case 'generation_in_progress':
      return problem('이 대화가 다른 답을 쓰는 중입니다. 끝난 뒤에 다시 해 주세요.', { reload: true });
    case 'not_continuable':
      return problem('이어 쓸 수 없는 말입니다. 끊긴 답이 가지의 끝일 때만 이어 씁니다.', { reload: true });
    case 'not_regenerable':
      return problem('인사말은 다시 생성할 수 없습니다.');
    case 'too_many_attempts':
      return problem(`너무 자주 보냈습니다.${error.retryAfter ? ` ${error.retryAfter}초 뒤에` : ' 잠시 뒤에'} 다시 보내 주세요.`);
    default:
      break;
  }
  if (error.status === 404) return problem('대화나 말을 찾지 못했습니다. 화면을 새로 읽습니다.', { reload: true });
  if (error.status === 422) return problem(Object.values(error.fields)[0]?.[0] ?? '보낼 수 없는 말입니다.');
  if (error.status === 503) {
    return problem(`지금은 답할 수 없습니다.${error.retryAfter ? ` ${error.retryAfter}초 뒤에` : ' 잠시 뒤에'} 다시 시도하세요.${tail}`, { reload: saved });
  }
  return problem('답을 받지 못했습니다. 잠시 뒤에 다시 시도하세요.', { reload: true });
}

/** 모델 바꾸기와 대안 고르기의 실패 */
export function describeChangeProblem(error: unknown): string {
  if (error instanceof NetworkError) return '서버에 닿지 못했습니다. 연결을 확인하고 다시 시도하세요.';
  if (error instanceof ApiError && error.code === 'generation_in_progress') return '답을 쓰는 중에는 바꿀 수 없습니다. 끝난 뒤에 해 주세요.';
  if (error instanceof ApiError && error.code === 'model_unavailable') return '이 대화에 고를 수 없는 모델입니다. 다른 모델을 골라 주세요.';
  if (error instanceof ApiError && error.code === 'not_editable') return '고칠 수 없는 말입니다. 내 말은 새 가지로 고칩니다.';
  if (error instanceof ApiError && error.status === 422) return Object.values(error.fields)[0]?.[0] ?? '고칠 수 없는 글입니다.';
  if (error instanceof ApiError && error.status === 503) return '모델의 값을 받지 못했습니다. 잠시 뒤에 다시 시도하세요.';
  if (error instanceof ApiError && error.code === 'too_many_attempts') return `너무 자주 바꿨습니다.${error.retryAfter ? ` ${error.retryAfter}초 뒤에` : ' 잠시 뒤에'} 다시 해 주세요.`;
  return '바꾸지 못했습니다. 잠시 뒤에 다시 시도하세요.';
}
