// web/apps/web/src/pages/operator/inquiries/InquiryActions.tsx
// 지운 기록. 문의를 지운 일마다 누가(정리 명령이면 정리 명령), 어떻게(하나, 고른 것, 상자 비움, 보관 기간), 몇 개, 언제.
// 지운 문의의 글은 남지 않는다(번호만). 기록도 1년 뒤에 지워진다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { formatDateTime } from '../../../format/dateTime';
import { inquiryActionsQuery } from './inquiryBoxQueries';
import { actionLine } from './inquiryBoxView';

export function InquiryActions() {
  const query = useInfiniteQuery(inquiryActionsQuery());
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <section className="inquiry-box" aria-label="지운 기록">
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError && items.length === 0 ? (
        <Notice tone="error">
          불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.isSuccess && items.length === 0 ? <p className="empty-state">아직 지운 문의가 없습니다.</p> : null}
      {items.length > 0 ? (
        <ul className="plain-list inquiry-actions" aria-label="지운 일">
          {items.map((action) => (
            <li key={action.id} className="inquiry-actions__row">
              <span>{actionLine(action)}</span>
              <span className="inquiry-actions__date">{formatDateTime(action.created_at)}</span>
            </li>
          ))}
        </ul>
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
