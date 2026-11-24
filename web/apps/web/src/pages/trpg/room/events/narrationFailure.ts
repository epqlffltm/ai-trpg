// web/apps/web/src/pages/trpg/room/events/narrationFailure.ts
// 서술의 실패(narration_failed)에 서버가 적은 까닭(reason)을 사람이 읽는 말로. 순수한 함수다.
// 서버의 까닭은 코드다(trpg-server/app/rounds/closing.py 의 failure_reason). 결제(insufficient_credits …),
// 모델 창구(timeout, status_429 …, shared/ai-core), 서술자(cut_off, empty …, app/rounds/llm_narrator.py)에서 온다.
// 코드를 그대로 보이지 않는다. 모르는 코드는 까닭 없이 "서술에 실패했습니다"로 둔다.

/** 까닭마다 "…해" 꼴의 말. 뒤에 "서술하지 못했습니다"가 붙는다 */
const CAUSES: Record<string, string> = {
  insufficient_credits: '크레딧이 모자라',
  gold_required: '골드가 모자라',
  model_not_for_sale: '서술 모델을 지금 팔지 않아',
  billing_unavailable: '결제 서버에 닿지 못해',
  timeout: '모델이 제때 답하지 않아',
  interrupted: '모델의 답이 끊겨',
  stream_error: '모델의 답이 끊겨',
  unreachable: '모델에 닿지 못해',
  status_429: '모델이 지금 바빠',
  malformed: '모델의 답을 읽지 못해',
  not_json: '모델의 답을 읽지 못해',
  generation_failed: '모델이 답을 만들지 못해',
  empty: '모델이 빈 답을 내',
  cut_off: '모델의 답이 중간에 잘려',
  too_long: '모델의 답이 너무 길어',
  secret_leaked: '모델의 답이 숨긴 이름을 드러내',
  no_story: '이야기의 바탕이 없어',
  model_unavailable: '서술 모델을 쓸 수 없어',
  provider_not_configured: '서술 모델을 쓸 수 없어',
  provider_unsupported: '서술 모델을 쓸 수 없어',
  status_401: '서술 모델을 쓸 수 없어',
  status_403: '서술 모델을 쓸 수 없어',
};

/** 까닭의 말. 모르는 코드나 없으면 null */
export function failureCause(reason: string | null | undefined): string | null {
  if (!reason) return null;
  // 제 칸만 본다. in 은 constructor 같은 물려받은 이름도 찾는다
  if (Object.hasOwn(CAUSES, reason)) return CAUSES[reason] ?? null;
  // 그 밖의 5xx 는 창구 쪽의 고장이다
  if (/^status_5\d\d$/.test(reason)) return '모델 쪽에 문제가 있어';
  return null;
}

/** 실패 한 줄의 뒷부분. "크레딧이 모자라 서술하지 못했습니다." 또는 "서술에 실패했습니다." */
export function failureText(reason: string | null | undefined): string {
  const cause = failureCause(reason);
  return cause ? `${cause} 서술하지 못했습니다.` : '서술에 실패했습니다.';
}
