// web/apps/web/src/api/refresh.ts
// refresh 쿠키로 새 access 토큰을 받는다. 한 번에 하나만 보낸다(#30).
//
// 같은 refresh 토큰으로 두 요청이 동시에 가면 인증 서버는 폐기된 토큰의 재사용으로 보고 모든 세션을 끊는다.
//   - 한 창 안: 진행 중인 갱신이 있으면 새로 보내지 않고 그 결과를 함께 기다린다(inflight).
//   - 창 사이: 탭 둘이 같은 쿠키를 쓴다. Web Locks 로 한 탭씩 차례로 보낸다. 앞 탭이 쿠키를 새것으로 바꾼 뒤에
//     다음 탭이 보내므로 재사용이 되지 않는다. Web Locks 가 없는 브라우저는 창 안의 하나만 지킨다.
//
// 401 이면 로그인이 끝난 것이다(쿠키가 없거나 폐기됨). 상태를 비우고 null 을 준다.
// 403 network_blocked(운영자가 막은 IP, #638)도 이 기기에서는 로그인이 끝난 것으로 본다. 로그인 화면이 까닭을 알린다.
// 서버는 쿠키를 지우지 않으므로, 다른 네트워크로 옮기거나 막기가 풀리면 새로 열 때 되살아난다.
// 그 밖의 실패(503, 연결 끊김)는 로그아웃시키지 않는다. 오류를 던지고 상태는 그대로 둔다(화면 명세의 공통 상태).

import { isNetworkBlocked, NetworkError, toApiError } from './errors';
import { clearSession, storeTokens, type Session } from './session';
import type { LoginResponse } from './types';

export const REFRESH_PATH = '/api/v1/auth/refresh';
const LOCK_NAME = 'ai-trpg-refresh';

let inflight: Promise<Session | null> | null = null;

export function refreshSession(): Promise<Session | null> {
  inflight ??= withRefreshLock(requestRefresh).finally(() => {
    inflight = null;
  });
  return inflight;
}

async function requestRefresh(): Promise<Session | null> {
  const response = await postRefresh();
  if (response.status === 401) {
    clearSession();
    return null;
  }
  if (response.ok) return storeTokens((await response.json()) as LoginResponse);
  const error = await toApiError(response);
  if (isNetworkBlocked(error)) {
    clearSession();
    return null;
  }
  throw error;
}

async function postRefresh(): Promise<Response> {
  try {
    return await fetch(REFRESH_PATH, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    });
  } catch (error) {
    throw new NetworkError(error);
  }
}

/** 탭 사이에서 하나씩. Web Locks 가 없으면(오래된 브라우저, 시험의 jsdom) 그냥 한다 */
async function withRefreshLock<T>(work: () => Promise<T>): Promise<T> {
  const locks = globalThis.navigator?.locks;
  if (!locks) return work();
  return await locks.request(LOCK_NAME, work);
}
