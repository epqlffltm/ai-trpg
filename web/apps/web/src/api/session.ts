// web/apps/web/src/api/session.ts
// 로그인한 상태(access 토큰)를 메모리에만 둔다. localStorage 에 두지 않는다(화면 명세의 A2).
// 창을 새로 열면 비어 있고, refresh 쿠키(httpOnly)로 다시 받는다(refresh.ts).
// 화면은 subscribe 로 바뀐 것을 듣는다(useSession).

import type { LoginResponse } from './types';

export type Session = {
  accessToken: string;
  /** 다시 동의할 필수 항목. 비어 있지 않으면 토큰이 인증 서버에만 통한다(#450) */
  consentsPending: string[];
  /** 탈퇴를 요청했으면 비울 시각. 있으면 토큰이 인증 서버에만 통한다(#603) */
  withdrawalScheduledAt: string | null;
};

let current: Session | null = null;
const listeners = new Set<() => void>();

export function getSession(): Session | null {
  return current;
}

export function subscribeSession(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** 토큰을 주는 응답(로그인, 갱신)을 지금의 상태로 둔다 */
export function storeTokens(response: LoginResponse): Session {
  return replaceSession({
    accessToken: response.access_token,
    consentsPending: response.consents_pending,
    withdrawalScheduledAt: response.withdrawal_scheduled_at,
  });
}

export function clearSession(): void {
  replaceSession(null);
}

/** 인증 서버 밖의 서버에는 통하지 않는 토큰인가(다시 동의하거나 탈퇴를 기다리는 중) */
export function isLimited(session: Session): boolean {
  return session.consentsPending.length > 0 || session.withdrawalScheduledAt !== null;
}

function replaceSession<T extends Session | null>(next: T): T {
  current = next;
  for (const listener of listeners) listener();
  return next;
}
