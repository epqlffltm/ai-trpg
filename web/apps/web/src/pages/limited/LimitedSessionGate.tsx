// web/apps/web/src/pages/limited/LimitedSessionGate.tsx
// 토큰이 인증 서버에만 통하는 동안 경로의 화면 대신 그리는 것(AppLayout). 다른 서버는 모두 401 이라 화면마다 다루지 않고 여기서 막는다.
// 탈퇴 유예가 먼저다. 취소한 뒤에도 다시 동의할 것이 남았으면 그다음에 다시 동의를 보인다.

import type { Session } from '../../api/session';
import { ReconsentPage } from './ReconsentPage';
import { WithdrawalPendingPage } from './WithdrawalPendingPage';

export function LimitedSessionGate({ session }: { session: Session }) {
  if (session.withdrawalScheduledAt) return <WithdrawalPendingPage scheduledAt={session.withdrawalScheduledAt} />;
  return <ReconsentPage />;
}
