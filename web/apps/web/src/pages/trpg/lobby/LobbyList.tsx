// web/apps/web/src/pages/trpg/lobby/LobbyList.tsx
// 로비의 공개 테이블. 모집 중이고 자리가 남은 것만, 최근에 만든 것부터. 실시간이 아니다. 열 때와 "새로 고치기"로 읽는다.
// 들어가기: 비밀번호가 없으면 바로, 있으면 창에서 받는다. 들어가면 테이블 방(B6)으로 간다.
// 목록은 들어가는 순간에 달라졌을 수 있다(자리가 참, 시작함). 정상 흐름으로 보고 알린 뒤 목록을 다시 읽는다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import { joinPublicTable } from '../../../api/tables';
import type { TableSummary } from '../../../api/types';
import { ProblemNotice } from '../../../components/ProblemNotice';
import { useCountdown } from '../../../hooks/useCountdown';
import { lobbyQuery } from '../queries';
import { describeJoinProblem, type TableProblem } from '../tables/tableProblem';
import { useEnterTable } from '../tables/useEnterTable';
import { LobbyCard } from './LobbyCard';
import { PasswordDialog } from './PasswordDialog';

type Props = { scenarioId: string | undefined; createPath: string };

export function LobbyList({ scenarioId, createPath }: Props) {
  const query = useInfiniteQuery(lobbyQuery(scenarioId));
  const tables = query.data?.pages.flatMap((page) => page.items) ?? [];
  const [asking, setAsking] = useState<TableSummary | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [problem, setProblem] = useState<TableProblem | undefined>();
  const wait = useCountdown();
  const enterTable = useEnterTable();

  async function join(table: TableSummary, password: string | null) {
    setBusyId(table.id);
    setProblem(undefined);
    try {
      const detail = await joinPublicTable(table.id, password);
      enterTable(detail.id);
    } catch (error) {
      await fail(table, describeJoinProblem(error));
      setBusyId(null);
    }
  }

  async function fail(table: TableSummary, next: TableProblem) {
    if (next.seated) return enterTable(table.id);
    setProblem(next);
    if (next.waitSeconds) wait.start(next.waitSeconds);
    if (next.refresh) {
      setAsking(null);
      await query.refetch();
    }
  }

  function start(table: TableSummary) {
    if (table.has_password) {
      setProblem(undefined);
      setAsking(table);
    } else {
      void join(table, null);
    }
  }

  return (
    <section aria-labelledby="lobby-heading">
      <div className="section-head">
        <h2 id="lobby-heading">모집 중인 테이블</h2>
        <Button variant="quiet" busy={query.isRefetching} onClick={() => void query.refetch()}>
          새로 고치기
        </Button>
      </div>
      {asking ? null : <ProblemNotice problem={problem} />}
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError && tables.length === 0 ? (
        <Notice tone="error">
          로비를 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.isSuccess && tables.length === 0 ? (
        <div className="empty-state">
          <p>지금 모집 중인 테이블이 없습니다.</p>
          <Link to={createPath}>첫 테이블을 만들어 보세요</Link>
        </div>
      ) : null}
      <ul className="lobby-list">
        {tables.map((table) => (
          <LobbyCard
            key={table.id}
            table={table}
            busy={busyId === table.id}
            disabled={busyId !== null || wait.remaining > 0}
            onJoin={() => start(table)}
          />
        ))}
      </ul>
      {query.hasNextPage ? (
        <div className="load-more">
          <Button variant="secondary" busy={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            더 보기
          </Button>
        </div>
      ) : null}
      <PasswordDialog
        table={asking}
        busy={asking !== null && busyId === asking.id}
        waitSeconds={wait.remaining}
        problem={problem}
        onClose={() => setAsking(null)}
        onSubmit={(password) => asking && void join(asking, password)}
      />
    </section>
  );
}
