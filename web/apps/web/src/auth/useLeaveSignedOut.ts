// web/apps/web/src/auth/useLeaveSignedOut.ts
// 로그인해야 열리는 화면에서 안내를 들고 로그인 화면으로 떠나며 이 기기의 상태를 비운다.
// 먼저 비우면 화면을 감싼 RequireSession 이 안내 없이 로그인으로 보내 버린다(경로의 이동은 늦게 그려지고, 상태를 비우는 것은 바로 그려진다).
// 그래서 옮기기만 하고, 이 화면이 내려갈 때 비운다. 로그인 화면을 넣는 바로 그 커밋 안에서 비운다(useLayoutEffect 의 정리).
// useEffect 의 정리는 화면을 그린 뒤 따로 돌아, 붐비면 로그인 화면이 보이는데 이 기기의 상태가 남은 틈이 생긴다.

import { useCallback, useLayoutEffect, useRef } from 'react';
import { useNavigate } from 'react-router';
import { clearSession } from '../api/session';

export function useLeaveSignedOut(): (notice: string) => void {
  const navigate = useNavigate();
  const leaving = useRef(false);

  useLayoutEffect(
    () => () => {
      if (leaving.current) clearSession();
    },
    [],
  );

  return useCallback(
    (notice: string) => {
      leaving.current = true;
      void navigate('/login', { replace: true, state: { notice } });
    },
    [navigate],
  );
}
