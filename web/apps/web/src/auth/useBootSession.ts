// web/apps/web/src/auth/useBootSession.ts
// 화면을 처음 열 때 refresh 쿠키로 로그인을 되살린다. 토큰은 메모리에만 있어 새로 열면 비어 있다.
//
// 개발 중의 StrictMode 는 이 효과를 두 번 돌린다. 갱신은 refreshSession 이 하나로 모으므로 두 번 가지 않는다(#30).
// 서버에 닿지 못하거나 서버가 답하지 않으면(5xx, 연결 끊김) 'unavailable' 과 그 실패를 돌려준다. 로그아웃시키지는 않는다.
// 틀(AppLayout)이 장애 화면을 그리고, 다시 시도(retry)하면 한 번 더 되살린다.

import { useCallback, useEffect, useState } from 'react';
import { refreshSession } from '../api/refresh';

export type BootState = 'checking' | 'ready' | 'unavailable';

export type Boot = { state: BootState; error: unknown; retry: () => void };

export function useBootSession(): Boot {
  const [state, setState] = useState<BootState>('checking');
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    refreshSession().then(
      () => {
        if (active) setState('ready');
      },
      (failure: unknown) => {
        if (!active) return;
        setError(failure);
        setState('unavailable');
      },
    );
    return () => {
      active = false;
    };
  }, [attempt]);

  const retry = useCallback(() => {
    setState('checking');
    setError(null);
    setAttempt((before) => before + 1);
  }, []);

  return { state, error, retry };
}
