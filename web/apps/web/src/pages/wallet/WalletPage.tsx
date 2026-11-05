// web/apps/web/src/pages/wallet/WalletPage.tsx
// 지갑(A6, Stitch 10번 "내 포인트"와 34번). 위에 잔액(골드, 실버, 곧 사라질 실버)의 카드, 그 아래 넓으면 두 칸:
// 왼쪽 넓은 칸에 자동 충전(#980)과 최근 자동 결제, 오른쪽 좁은 칸에 쿠폰 넣기(#979). 맨 아래에 원장(최근 것부터, 더 보기).
// 좁으면 잔액, 쿠폰, 자동 충전, 최근 자동 결제, 원장의 차례로 위아래다(쿠폰이 짧아 먼저 둔다).
// 로그인해야 열린다(App.tsx 의 RequireSession). 충전(A7), 출석(A9), 주문 내역(A8)으로 가는 길은 잔액 아래에 있다.

import { AutoChargeHistory } from './AutoChargeHistory';
import { AutoChargeSection } from './AutoChargeSection';
import { CouponForm } from './CouponForm';
import { WalletBalance } from './WalletBalance';
import { WalletLedger } from './WalletLedger';

export function WalletPage() {
  return (
    <main className="page wallet">
      <h1>지갑</h1>
      <p className="hint">골드는 산 크레딧, 실버는 무료로 받은 크레딧입니다. 서술 값을 냅니다. 게임 안의 돈과는 다릅니다.</p>
      <WalletBalance />
      <div className="wallet__columns">
        <div className="wallet__side">
          <CouponForm />
        </div>
        <div className="wallet__main">
          <AutoChargeSection />
          <AutoChargeHistory />
        </div>
      </div>
      <WalletLedger />
    </main>
  );
}
