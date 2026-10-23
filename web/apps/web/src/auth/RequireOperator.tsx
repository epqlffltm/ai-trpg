// web/apps/web/src/auth/RequireOperator.tsx
// 운영자의 화면(E4)을 감싼다. 운영자가 아니면 없는 화면처럼 보인다(서버의 /admin API 가 404 인 것과 같다).
// 로그인했는지는 바깥의 RequireSession 이 먼저 본다.

import type { ReactNode } from 'react';
import { NotFoundPage } from '../pages/NotFoundPage';
import { isOperator } from './roles';
import { useSession } from './useSession';

export function RequireOperator({ children }: { children: ReactNode }) {
  const session = useSession();
  return isOperator(session) ? children : <NotFoundPage />;
}
