// web/apps/web/src/layout/HeaderBalance.tsx
// 머리의 잔액(A6). "골드 80 · 실버 10" 을 지갑으로 잇는다. 로그인했을 때만 둔다(AppHeader).
// 읽지 못했으면(결제 서버가 503 이거나 아직 읽는 중) 아무것도 보이지 않는다. 머리 때문에 화면이 깨지지 않게.
// 다시 읽는 때는 walletQueries.ts 에 적었다(화면에 돌아올 때, 크레딧을 바꿀 수 있는 테이블의 일).

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { walletQuery } from '../pages/wallet/walletQueries';
import { balanceShort } from '../pages/wallet/walletView';

export function HeaderBalance() {
  const wallet = useQuery(walletQuery());
  if (!wallet.data) return null;
  return (
    <Link to="/wallet" className="app-header__balance" aria-label={`지갑: ${balanceShort(wallet.data)}`}>
      {balanceShort(wallet.data)}
    </Link>
  );
}
