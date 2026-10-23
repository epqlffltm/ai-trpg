// web/apps/web/src/pages/wallet/WalletPage.tsx
// 지갑(A6). 위에 잔액(골드, 실버, 곧 사라질 실버), 아래에 원장(최근 것부터, 더 보기). 읽기만 한다.
// 로그인해야 열린다(App.tsx 의 RequireSession). 충전(A7)과 출석(A9)은 아직 화면이 없어 글로만 알린다.

import { WalletBalance } from './WalletBalance';
import { WalletLedger } from './WalletLedger';

export function WalletPage() {
  return (
    <main className="page page--medium">
      <h1>지갑</h1>
      <p className="hint">골드는 산 크레딧, 실버는 무료로 받은 크레딧입니다. 서술 값을 냅니다. 게임 안의 돈과는 다릅니다.</p>
      <WalletBalance />
      <WalletLedger />
    </main>
  );
}
