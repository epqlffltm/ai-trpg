// web/apps/web/src/pages/me/MyAttendance.tsx
// 마이페이지 "내 포인트" 탭의 출석(Stitch 10번의 "출석체크로 실버 얻기"). 출석 화면을 따로 열지 않고 이 자리에서
// 주기의 칸과 오늘 받기(AttendanceToday)를 보이고, 보물 상자의 확률표는 접어 둔다(펼치면 보인다).
// 출석 화면(/wallet/attendance)으로 가는 길도 남긴다. 읽지 못하면 한 줄로 알리고 다시 시도를 둔다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { attendanceProblemText } from '../attendance/attendanceProblem';
import { attendanceQuery, rewardsQuery } from '../attendance/attendanceQueries';
import { AttendanceToday } from '../attendance/AttendanceToday';
import { ChestOdds } from '../attendance/ChestOdds';

export function MyAttendance() {
  const status = useQuery(attendanceQuery());
  const rewards = useQuery(rewardsQuery());
  const failed = status.error ?? rewards.error;
  return (
    <section className="page-section my-attendance" aria-labelledby="my-attendance-heading">
      <h2 id="my-attendance-heading">출석체크로 실버 얻기</h2>
      <p className="hint">
        하루에 한 번 실버를 받습니다. 하루라도 빠지면 1일째부터 다시 셉니다. <Link to="/wallet/attendance">출석 화면</Link>
      </p>
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
      {status.data && rewards.data ? <AttendanceToday status={status.data} rewards={rewards.data} /> : null}
      {rewards.data ? (
        <details className="my-attendance__odds">
          <summary>출석 보물상자 획득 확률 안내</summary>
          <ChestOdds chest={rewards.data.chest} />
        </details>
      ) : null}
    </section>
  );
}
