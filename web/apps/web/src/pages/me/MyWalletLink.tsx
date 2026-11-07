// web/apps/web/src/pages/me/MyWalletLink.tsx
// 마이페이지 "내 포인트" 탭의 지갑(Stitch 10번). 카드 둘(골드: 잔액, "충전", "내역" / 실버: 잔액, 곧 사라질 실버, "내역")과
// 그 아래 지갑(A6)의 다른 화면으로 가는 길(주문 내역, 출석). 잔액을 읽지 못해도 카드의 길은 둔다.

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { useNow } from '../../hooks/useNow';
import { walletQuery } from '../wallet/walletQueries';
import { expiryText } from '../wallet/walletView';

export function MyWalletLink() {
  const wallet = useQuery(walletQuery());
  const now = useNow(60_000);
  const expiry = wallet.data ? expiryText(wallet.data, now) : null;
  return (
    <section className="page-section" aria-labelledby="my-wallet-heading">
      <h2 id="my-wallet-heading">지갑</h2>
      <div className="my-points">
        <section className="my-points__card my-points__card--gold" aria-label="골드">
          <p className="my-points__label">골드</p>
          <p className="my-points__amount">{wallet.data?.paid ?? '-'}</p>
          <p className="my-points__links">
            <Link to="/wallet/charge">충전</Link> · <Link to="/wallet">내역</Link>
          </p>
        </section>
        <section className="my-points__card" aria-label="실버">
          <p className="my-points__label">실버</p>
          <p className="my-points__amount">{wallet.data?.free ?? '-'}</p>
          {expiry ? <p className="hint">{expiry}</p> : null}
          <p className="my-points__links">
            <Link to="/wallet">내역</Link>
          </p>
        </section>
      </div>
      <p>
        <Link to="/wallet">잔액과 내역 보기</Link> · <Link to="/wallet/orders">주문 내역</Link> · <Link to="/wallet/attendance">출석</Link>
      </p>
    </section>
  );
}
