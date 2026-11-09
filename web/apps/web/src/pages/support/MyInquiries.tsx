// web/apps/web/src/pages/support/MyInquiries.tsx
// 내 문의(로그인했을 때만). 최근 것부터 한 줄에 종류, 제목, 상태, 보낸 날. 펼치면 보낸 내용과 답.
// 답은 메일로도 간다. 보관은 보낸 지 1년이다(그 뒤에는 서버가 지운다).

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import type { MyInquiry } from '../../api/inquiries';
import { formatDate, formatDateTime } from '../../format/dateTime';
import { categoryLabel, statusLabel } from './inquiryView';
import { myInquiriesQuery } from './supportQueries';

export function MyInquiries() {
  const query = useInfiniteQuery(myInquiriesQuery());
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <section className="page-section" aria-labelledby="my-inquiries-heading">
      <h2 id="my-inquiries-heading">내 문의</h2>
      <p className="hint">보낸 지 1년이 지난 문의는 지워집니다.</p>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError && items.length === 0 ? (
        <Notice tone="error">
          불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.isSuccess && items.length === 0 ? <p className="empty-state">아직 보낸 문의가 없습니다.</p> : null}
      {items.length > 0 ? (
        <ul className="plain-list my-inquiries" aria-label="내 문의">
          {items.map((inquiry) => (
            <MyInquiryRow key={inquiry.id} inquiry={inquiry} />
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

function MyInquiryRow({ inquiry }: { inquiry: MyInquiry }) {
  return (
    <li className="my-inquiry">
      <details>
        <summary>
          <span className="my-inquiry__category">{categoryLabel(inquiry.category)}</span>
          <span className="my-inquiry__title">{inquiry.title}</span>
          <span className={`my-inquiry__status my-inquiry__status--${inquiry.status}`}>{statusLabel(inquiry.status)}</span>
          <span className="my-inquiry__date">{formatDate(inquiry.created_at)}</span>
        </summary>
        <p className="my-inquiry__body">{inquiry.body}</p>
        {inquiry.answered_at ? (
          <div className="my-inquiry__reply" aria-label="답">
            <p className="hint">{formatDateTime(inquiry.answered_at)}에 답했습니다.</p>
            <p>{inquiry.reply}</p>
          </div>
        ) : (
          <p className="hint">아직 답하지 않았습니다.</p>
        )}
      </details>
    </li>
  );
}
