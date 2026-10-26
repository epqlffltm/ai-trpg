// web/apps/web/src/pages/operator/BoardReportSection.tsx
// 게시판의 신고(board). 열린 신고를 글이나 댓글마다 한 줄로 묶어 보인다. 처음 신고가 이른 것부터다.
// 한 줄을 펼치면 신고 하나하나(설명, 처리한 것까지)와 닫기가 나온다. 닫으면 그 줄은 목록에서 빠진다.
// 글이나 댓글을 지우는 것은 그 글의 화면(게시판)에서 한다. 지운 것은 "지움" 표가 붙고, 닫아야 목록에서 빠진다.

import { useInfiniteQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import type { BoardReportGroup } from '../../api/boardReports';
import { formatDateTime } from '../../format/dateTime';
import { BoardReportDetail } from './BoardReportDetail';
import { boardReasonSummary, targetLabel, targetPostPath } from './boardReportView';
import { LoadMore } from './LoadMore';
import { boardGroupsQuery } from './moderationQueries';

export function BoardReportSection() {
  const query = useInfiniteQuery(boardGroupsQuery());
  const groups = query.data?.pages.flatMap((page) => page.items) ?? [];
  const total = query.data?.pages[0]?.total ?? 0;
  return (
    <section className="page-section" aria-labelledby="board-reports">
      <h2 id="board-reports">게시판의 신고 {query.isSuccess ? <small>({total}개)</small> : null}</h2>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isSuccess && groups.length === 0 ? <p className="empty-state">열린 신고가 없습니다.</p> : null}
      <ul className="plain-list moderation-list" aria-label="신고된 글과 댓글">
        {groups.map((group) => (
          <BoardGroupItem key={`${group.target.type}-${group.target.id}`} group={group} />
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

function BoardGroupItem({ group }: { group: BoardReportGroup }) {
  const [open, setOpen] = useState(false);
  const path = targetPostPath(group.target);
  return (
    <li className="moderation-list__item">
      <p>
        <strong>{targetLabel(group.target)}</strong> {group.target.deleted ? <span className="badge">지움</span> : null} 열린 신고 {group.open_count}건
        {path ? (
          <>
            {' '}
            <Link to={path}>글 보기</Link>
          </>
        ) : null}
      </p>
      <p>{boardReasonSummary(group.reasons)}</p>
      <p className="hint">
        처음 {formatDateTime(group.first_reported_at)} · 마지막 {formatDateTime(group.last_reported_at)}
      </p>
      <details onToggle={(event) => setOpen(event.currentTarget.open)}>
        <summary>신고 보기와 처리</summary>
        {open ? <BoardReportDetail target={group.target} /> : null}
      </details>
    </li>
  );
}
