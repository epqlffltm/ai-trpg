// web/apps/web/src/pages/operator/BoardReportDetail.tsx
// 글이나 댓글 하나에 걸린 신고 모두(처리한 것까지, 최근 것부터)와 닫기. 신고한 사람의 id 는 운영자만 본다.
// 닫기는 열린 신고를 한 번에 모두 "조치함"이나 "문제없음"으로 닫는다. 게시판 서버는 운영자의 사유를 받지 않는다.
// 닫으면 게시판의 신고 목록을 다시 읽는다(그 줄이 빠진다). 이미 다른 운영자가 닫았으면(404) 알리고 목록을 다시 읽는다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../../api/errors';
import { closeBoardReports, type BoardReport, type BoardReportOutcome, type BoardReportTarget } from '../../api/boardReports';
import { ProblemNotice } from '../../components/ProblemNotice';
import { formatDateTime } from '../../format/dateTime';
import { boardOutcomeLabel, boardReasonLabel } from './boardReportView';
import { LoadMore } from './LoadMore';
import { describeModerationProblem, type ModerationProblem } from './moderationProblem';
import { boardGroupsQuery, boardItemReportsQuery } from './moderationQueries';

export function BoardReportDetail({ target }: { target: BoardReportTarget }) {
  const query = useInfiniteQuery(boardItemReportsQuery(target));
  const closing = useCloseReports(target);
  const reports = query.data?.pages.flatMap((page) => page.items) ?? [];
  const problem = closing.error ? describeCloseProblem(closing.error) : undefined;

  if (query.isPending) return <p aria-busy="true">불러오는 중</p>;
  return (
    <div className="moderation-detail">
      <ol className="plain-list" aria-label="이 글이나 댓글의 신고">
        {reports.map((report) => (
          <ReportLine key={report.id} report={report} />
        ))}
      </ol>
      <LoadMore
        failed={query.isError}
        hasMore={query.hasNextPage}
        loadingMore={query.isFetchingNextPage}
        onRetry={() => void query.refetch()}
        onMore={() => void query.fetchNextPage()}
      />
      <p className="hint">열린 신고를 모두 한꺼번에 닫습니다. 지우는 것은 글의 화면에서 따로 합니다.</p>
      <ProblemNotice problem={problem} />
      {closing.isSuccess ? <Notice tone="info">닫았습니다.</Notice> : null}
      <div className="actions">
        <Button busy={closing.isPending && closing.variables === 'actioned'} disabled={closing.isPending} onClick={() => closing.mutate('actioned')}>
          조치함으로 닫기
        </Button>
        <Button variant="secondary" busy={closing.isPending && closing.variables === 'dismissed'} disabled={closing.isPending} onClick={() => closing.mutate('dismissed')}>
          문제없음으로 닫기
        </Button>
      </div>
    </div>
  );
}

/** 닫고 나서(또는 이미 닫혀 404 면) 게시판의 신고 목록과 이 신고들을 다시 읽는다 */
function useCloseReports(target: BoardReportTarget) {
  const queryClient = useQueryClient();
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: boardGroupsQuery().queryKey });
  };
  return useMutation({
    mutationFn: (outcome: BoardReportOutcome) => closeBoardReports(target, outcome),
    onSuccess: refresh,
    onError: async (error) => {
      if (describeCloseProblem(error).refresh) await refresh();
    },
  });
}

/** 게시판 서버의 404 는 닫을 열린 신고가 없다는 것이다(다른 운영자가 먼저 닫았다) */
function describeCloseProblem(error: unknown): ModerationProblem {
  if (error instanceof ApiError && error.status === 404) return { message: '닫을 열린 신고가 없습니다. 다른 운영자가 먼저 닫았을 수 있습니다.', refresh: true };
  return describeModerationProblem(error);
}

function ReportLine({ report }: { report: BoardReport }) {
  return (
    <li className="moderation-report">
      <p>
        <strong>{boardReasonLabel(report.reason)}</strong> · {boardOutcomeLabel(report)}
        {report.handled_at ? ` · ${formatDateTime(report.handled_at)}에 처리` : ''}
      </p>
      {report.description ? <p className="moderation-report__text">{report.description}</p> : null}
      <p className="hint">
        {formatDateTime(report.created_at)} · 신고한 사람 {report.reporter_id ?? '탈퇴함'}
      </p>
    </li>
  );
}
