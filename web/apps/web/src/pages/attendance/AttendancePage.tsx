// web/apps/web/src/pages/attendance/AttendancePage.tsx
// 출석·보물 상자(A9, /wallet/attendance). 하루에 한 번 실버를 받고, 주기의 마지막 날에는 보물 상자를 연다.
// 위에 오늘(주기의 칸, 오늘의 양, 받기), 아래에 보물 상자의 확률표. 로그인해야 열린다(App.tsx 의 RequireSession).
// 오늘의 칸과 받기는 AttendanceToday 다(마이페이지 내 포인트 탭과 함께 쓴다).

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { attendanceProblemText } from './attendanceProblem';
import { attendanceQuery, rewardsQuery } from './attendanceQueries';
import { AttendanceToday } from './AttendanceToday';
import { ChestOdds } from './ChestOdds';

export function AttendancePage() {
  const status = useQuery(attendanceQuery());
  const rewards = useQuery(rewardsQuery());
  const failed = status.error ?? rewards.error;
  return (
    <main className="page page--medium">
      <p>
        <Link to="/wallet">지갑</Link>
      </p>
      <h1>출석</h1>
      <p className="hint">하루에 한 번 실버를 받습니다. 하루라도 빠지면 1일째부터 다시 셉니다. 날짜는 한국 시각 자정에 바뀝니다.</p>
      {status.isPending || rewards.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {failed ? (
        <Notice tone="error">
          {attendanceProblemText(failed)}{' '}
          <Button
            variant="quiet"
            onClick={() => {
              void status.refetch();
              void rewards.refetch();
            }}
          >
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {status.data && rewards.data ? (
        <section className="page-section" aria-labelledby="attendance-today-heading">
          <h2 id="attendance-today-heading">오늘</h2>
          <AttendanceToday status={status.data} rewards={rewards.data} />
        </section>
      ) : null}
      {rewards.data ? <ChestOdds chest={rewards.data.chest} /> : null}
    </main>
  );
}
