// web/apps/web/src/auth/useSession.ts
// 지금의 로그인 상태를 화면에서 읽는다. 바뀌면(로그인, 갱신, 로그아웃) 다시 그린다.

import { useSyncExternalStore } from 'react';
import { getSession, subscribeSession, type Session } from '../api/session';

export function useSession(): Session | null {
  return useSyncExternalStore(subscribeSession, getSession, getSession);
}
