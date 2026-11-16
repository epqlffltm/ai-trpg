// web/apps/web/src/api/stepUp.ts
// 민감한 작업(청약철회, 카드 등록·바꾸기·지우기) 앞의 본인 확인(인증 서버, F5). auth-server/README.md 의 "민감한 작업의 본인 확인".
//
//   - 창은 세션(토큰의 sid)마다 있다. 메일 코드로 확인하면 이 세션의 창이 10분 열린다
//   - 확인을 끌 수 있다. 끄는 것은 창이 열린 동안에만 된다(아니면 403 step_up_required)
//   - sid 가 없는 옛 토큰이면 409 step_up_session_unknown 이다. 갱신하면 sid 가 생기므로 한 번 갱신하고 다시 부른다
//
// 언제 확인을 받게 할지는 stepUpGate.ts 가 정한다. 여기는 부르기만 한다.

import { ApiError } from './errors';
import type { components } from './generated/auth';
import { apiRequest } from './http';
import { refreshSession } from './refresh';

const AUTH = '/api/v1/auth';

export type StepUpStatus = components['schemas']['StepUpStatus'];
export type StepUpCodeSent = components['schemas']['StepUpCodeSent'];

/** 이 세션의 확인 창. 켜져 있는지, 열려 있는지 */
export function fetchStepUp(signal?: AbortSignal): Promise<StepUpStatus> {
  return withSessionName(() => apiRequest<StepUpStatus>(`${AUTH}/me/step-up`, signal ? { signal } : {}));
}

/** 가입한 메일로 확인 코드를 보낸다. 앞서 보낸 코드를 아직 쓸 수 있으면 새로 보내지 않는다(sent: false) */
export function sendStepUpCode(): Promise<StepUpCodeSent> {
  return apiRequest<StepUpCodeSent>(`${AUTH}/me/step-up/code`, { method: 'POST' });
}

/** 메일로 받은 코드로 확인하고 이 세션의 창을 연다. 틀리면 400 step_up_code_invalid */
export function verifyStepUp(code: string): Promise<StepUpStatus> {
  return withSessionName(() => apiRequest<StepUpStatus>(`${AUTH}/me/step-up`, { method: 'POST', body: { code } }));
}

/** 본인 확인을 켜거나 끈다. 끄는 것은 창이 열린 동안에만 된다(403 step_up_required) */
export function setStepUpEnabled(enabled: boolean): Promise<StepUpStatus> {
  return withSessionName(() =>
    apiRequest<StepUpStatus>(`${AUTH}/me/step-up/setting`, { method: 'PUT', body: { enabled } }),
  );
}

/** 토큰에 세션의 이름이 없다는 답인가(이 기능 전에 받은 토큰) */
export function isSessionUnknown(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409 && error.code === 'step_up_session_unknown';
}

/** 부르고, 토큰에 세션의 이름이 없다는 답이면 한 번 갱신하고 다시 부른다. 갱신하지 못하면(로그인이 끝남) 처음 오류를 던진다 */
async function withSessionName<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch (error) {
    if (!isSessionUnknown(error)) throw error;
    if ((await refreshSession()) === null) throw error;
    return call();
  }
}
