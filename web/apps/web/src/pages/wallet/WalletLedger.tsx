// web/apps/web/src/pages/wallet/WalletLedger.tsx
// 지갑의 원장. 최근 것부터 한 쪽씩, "더 보기"로 앞의 것을 읽는다. 한 줄은 언제, 무엇(충전, 서술 값 …), 골드인지 실버인지, 늘고 준 양.
// 서술 값의 줄(hold)에는 그 홀드의 지금 상태를 붙인다(대기, 사용, 반환됨). 내부 정리(regroup)는 숨긴다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import type { WalletEntry } from '../../api/types';
import { formatDateTime } from '../../format/dateTime';
import { walletProblemText } from './walletProblem';
import { walletEntriesQuery } from './walletQueries';
import { entryDirection, entryLabel, kindLabel, signedAmount, visibleEntries } from './walletView';

export function WalletLedger() {
  const query = useInfiniteQuery(walletEntriesQuery());
  const entries = visibleEntries(query.data?.pages.flatMap((page) => page.entries) ?? []);
  return (
    <section className="page-section" aria-labelledby="ledger-heading">
      <h2 id="ledger-heading">내역</h2>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError ? (
        <Notice tone="error">
          {walletProblemText(query.error)}{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.isSuccess && entries.length === 0 && !query.hasNextPage ? <p className="hint">아직 내역이 없습니다.</p> : null}
      {entries.length > 0 ? (
        <ol className="plain-list ledger" aria-label="내역, 최근 것이 위">
          {entries.map((entry) => (
            <LedgerLine key={entry.id} entry={entry} />
          ))}
        </ol>
      ) : null}
      {query.hasNextPage ? (
        <div className="load-more">
          <Button variant="secondary" busy={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            더 보기
          </Button>
        </div>
      ) : null}
    </section>
  );
}

function LedgerLine({ entry }: { entry: WalletEntry }) {
  return (
    <li className={`ledger__line ledger__line--${entryDirection(entry)}`}>
      <span className="ledger__what">
        {entryLabel(entry)} <span className="hint">· {kindLabel(entry.kind)}</span>
      </span>
      <span className="ledger__amount">{signedAmount(entry.amount)}</span>
      <time className="hint ledger__when" dateTime={entry.created_at}>
        {formatDateTime(entry.created_at)}
      </time>
    </li>
  );
}
