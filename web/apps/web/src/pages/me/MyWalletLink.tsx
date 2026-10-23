// web/apps/web/src/pages/me/MyWalletLink.tsx
// 마이페이지의 "지갑". 지금 잔액 한 줄과 지갑(A6), 주문 내역(A8)으로 가는 길. 잔액을 읽지 못해도 길은 둔다.

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { walletQuery } from '../wallet/walletQueries';
import { balanceShort } from '../wallet/walletView';

export function MyWalletLink() {
  const wallet = useQuery(walletQuery());
  return (
    <section className="page-section" aria-labelledby="my-wallet-heading">
      <h2 id="my-wallet-heading">지갑</h2>
      {wallet.data ? <p>{balanceShort(wallet.data)}</p> : null}
      <p>
        <Link to="/wallet">잔액과 내역 보기</Link> · <Link to="/wallet/orders">주문 내역</Link>
      </p>
    </section>
  );
}
