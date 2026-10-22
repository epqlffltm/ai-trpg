// web/apps/web/src/auth/useBootSession.ts
// 화면을 처음 열 때 refresh 쿠키로 로그인을 되살린다. 토큰은 메모리에만 있어 새로 열면 비어 있다.
//
// 개발 중의 StrictMode 는 이 효과를 두 번 돌린다. 갱신은 refreshSession 이 하나로 모으므로 두 번 가지 않는다(#30).
// 서버가 잠시 답하지 않으면(503, 연결 끊김) 로그인하지 않은 채로 연다. 로그아웃시키지는 않는다.

import { useEffect, useState } from 'react';
import { refreshSession } from '../api/refresh';

export type BootState = 'checking' | 'ready' | 'unavailable';

export function useBootSession(): BootState {
  const [state, setState] = useState<BootState>('checking');
  useEffect(() => {
    let active = true;
    refreshSession().then(
      () => active && setState('ready'),
      () => active && setState('unavailable'),
    );
    return () => {
      active = false;
    };
  }, []);
  return state;
}
