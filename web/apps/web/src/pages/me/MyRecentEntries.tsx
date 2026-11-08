// web/apps/web/src/pages/me/MyRecentEntries.tsx
// 마이페이지 "내 포인트" 탭의 최근 사용 내역(Stitch 10번). 지갑의 원장에서 최근 다섯 줄을 표(때, 무엇에, 얼마)로 보이고, 전체는 지갑(A6)으로 간다.
// 원장의 앞 한 쪽만 읽는다. 내부 정리(regroup)는 지갑처럼 숨긴다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { formatDateTime } from '../../format/dateTime';
import { walletEntriesQuery } from '../wallet/walletQueries';
import { entryLabel, kindLabel, signedAmount, visibleEntries } from '../wallet/walletView';

/** 보일 줄의 수 */
export const RECENT_ENTRIES = 5;

export function MyRecentEntries() {
  const query = useInfiniteQuery(walletEntriesQuery());
  const entries = visibleEntries(query.data?.pages[0]?.entries ?? []).slice(0, RECENT_ENTRIES);
  return (
    <section className="page-section" aria-labelledby="my-recent-entries-heading">
      <h2 id="my-recent-entries-heading">최근 사용 내역</h2>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError ? (
        <Notice tone="error">
          불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.isSuccess && entries.length === 0 ? <p className="hint">아직 내역이 없습니다.</p> : null}
      {entries.length > 0 ? (
        <table className="my-entries">
          <thead>
            <tr>
              <th scope="col">때</th>
              <th scope="col">무엇에</th>
              <th scope="col">얼마</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id}>
                <td>
                  <time dateTime={entry.created_at}>{formatDateTime(entry.created_at)}</time>
                </td>
                <td>
                  {entryLabel(entry)} <span className="hint">· {kindLabel(entry.kind)}</span>
                </td>
                <td className="my-entries__amount">{signedAmount(entry.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      <p>
        <Link to="/wallet">전체 내역 보기</Link>
      </p>
    </section>
  );
}
