// web/apps/web/src/pages/operator/MessageReportSection.tsx
// 대화 속 답의 신고(chat). 미성년 사유가 먼저, 그다음 오래된 것부터. 목록에는 대화의 글이 없다.
// 글을 보려면 신고 하나로 가서 까닭을 적는다(MessageReportPage).

import { useInfiniteQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { formatDateTime } from '../../format/dateTime';
import { LoadMore } from './LoadMore';
import { reasonLabel } from './moderationPure';
import { messageReportsQuery } from './moderationQueries';

export function MessageReportSection() {
  const query = useInfiniteQuery(messageReportsQuery());
  const reports = query.data?.pages.flatMap((page) => page.items) ?? [];
  const total = query.data?.pages[0]?.total ?? 0;
  return (
    <section className="page-section" aria-labelledby="message-reports">
      <h2 id="message-reports">대화 속 답의 신고 {query.isSuccess ? <small>({total}건)</small> : null}</h2>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isSuccess && reports.length === 0 ? <p className="empty-state">열린 신고가 없습니다.</p> : null}
      <ul className="plain-list moderation-list" aria-label="신고된 답">
        {reports.map((report) => (
          <li key={report.id} className="moderation-list__item">
            <Link to={`/operator/reports/messages/${report.id}`}>
              {report.character_name}({report.character_version}번째 판)의 답
            </Link>
            <p>
              <strong>{reasonLabel(report.reason)}</strong>
              {report.model_slug ? ` · 모델 ${report.model_slug}` : null}
            </p>
            <p className="hint">{formatDateTime(report.created_at)}</p>
          </li>
        ))}
      </ul>
      <LoadMore
        failed={query.isError}
        hasMore={query.hasNextPage}
        loadingMore={query.isFetchingNextPage}
        onRetry={() => void query.refetch()}
        onMore={() => void query.fetchNextPage()}
      />
    </section>
  );
}
