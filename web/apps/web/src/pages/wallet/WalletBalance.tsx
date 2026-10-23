// web/apps/web/src/pages/wallet/WalletBalance.tsx
// 지갑의 잔액. 골드와 실버 두 칸, 합, 곧 사라질 실버. 서버가 준 글자를 그대로 보인다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { formatDateTime } from '../../format/dateTime';
import { useNow } from '../../hooks/useNow';
import { walletProblemText } from './walletProblem';
import { walletQuery } from './walletQueries';
import { expiryText } from './walletView';

const MINUTE_MS = 60_000;

export function WalletBalance() {
  const wallet = useQuery(walletQuery());
  const now = useNow(MINUTE_MS);
  return (
    <section className="page-section" aria-labelledby="balance-heading">
      <h2 id="balance-heading">잔액</h2>
      {wallet.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {wallet.isError ? (
        <Notice tone="error">
          {walletProblemText(wallet.error)}{' '}
          <Button variant="quiet" onClick={() => void wallet.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {wallet.data ? (
        <>
          <dl className="balance">
            <div className="balance__item">
              <dt>골드</dt>
              <dd>{wallet.data.paid}</dd>
            </div>
            <div className="balance__item">
              <dt>실버</dt>
              <dd>{wallet.data.free}</dd>
            </div>
            <div className="balance__item balance__item--total">
              <dt>합</dt>
              <dd>{wallet.data.total}</dd>
            </div>
          </dl>
          {wallet.data.next_expiry ? (
            <p className="hint">
              곧 사라질 {expiryText(wallet.data, now)}({formatDateTime(wallet.data.next_expiry.expires_at)})
            </p>
          ) : null}
          <p className="hint">충전과 출석은 준비 중입니다.</p>
        </>
      ) : null}
    </section>
  );
}
