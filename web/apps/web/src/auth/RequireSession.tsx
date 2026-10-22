// web/apps/web/src/auth/RequireSession.tsx
// 로그인해야 열리는 화면을 감싼다. 로그인하지 않았으면 로그인으로 보내고, 마치면 이 화면으로 돌아온다(state.from).
// 처음 열 때의 되살리기(refresh)는 AppLayout 이 마친 뒤에 화면을 그리므로 여기서 기다리지 않는다.

import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router';
import { useSession } from './useSession';

export function RequireSession({ children }: { children: ReactNode }) {
  const session = useSession();
  const location = useLocation();
  if (!session) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return children;
}
