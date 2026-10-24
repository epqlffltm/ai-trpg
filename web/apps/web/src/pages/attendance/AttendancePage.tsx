// web/apps/web/src/pages/attendance/AttendancePage.tsx
// 출석·보물 상자(A9, /wallet/attendance). 하루에 한 번 실버를 받고, 주기의 마지막 날에는 보물 상자를 연다.
// 위에 오늘(주기의 칸, 오늘의 양, 받기), 아래에 보물 상자의 확률표. 로그인해야 열린다(App.tsx 의 RequireSession).
// 본인인증 전이면 받기를 막고 까닭을 적는다. 받은 실버는 30일 뒤에 사라지고 스탠다드 모델에만 쓴다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import type { AttendanceClaim, AttendanceRewards, AttendanceStatus } from '../../api/types';
import { formatDateTime } from '../../format/dateTime';
import { AttendanceCycle } from './AttendanceCycle';
import { attendanceProblemText, VERIFY_FIRST } from './attendanceProblem';
import { attendanceQuery, rewardsQuery } from './attendanceQueries';
import { chestLine, claimButtonLabel, claimLine, cycleCells, todayLine } from './attendanceView';
import { ChestOdds } from './ChestOdds';
import { useClaimAttendance } from './useClaimAttendance';

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
      {status.data && rewards.data ? <Today status={status.data} rewards={rewards.data} /> : null}
      {rewards.data ? <ChestOdds chest={rewards.data.chest} /> : null}
    </main>
  );
}

function Today({ status, rewards }: { status: AttendanceStatus; rewards: AttendanceRewards }) {
  const claiming = useClaimAttendance();
  const blocked = !status.verified || status.claimed;
  return (
    <section className="page-section" aria-labelledby="attendance-today-heading">
      <h2 id="attendance-today-heading">오늘</h2>
      <AttendanceCycle cells={cycleCells(rewards.cycle, status)} />
      <p>{todayLine(status)}</p>
      {!status.verified ? (
        <Notice>
          {VERIFY_FIRST} <Link to="/me/identity">본인인증하기</Link>
        </Notice>
      ) : null}
      {claiming.problem ? <Notice tone="error">{claiming.problem}</Notice> : null}
      {claiming.claimed ? <ClaimResult claim={claiming.claimed} /> : null}
      <div className="form-actions">
        <Button busy={claiming.busy} disabled={blocked} onClick={() => void claiming.claim()}>
          {claimButtonLabel(status)}
        </Button>
      </div>
      <p className="hint">받은 실버는 30일 뒤에 사라지고, 프리미엄 서술 모델에는 쓰지 못합니다.</p>
    </section>
  );
}

function ClaimResult({ claim }: { claim: AttendanceClaim }) {
  const chest = chestLine(claim);
  return (
    <div className="attendance-result" role="status">
      <p>{claimLine(claim)}</p>
      {chest ? <p className="attendance-result__chest">{chest}</p> : null}
      <p className="hint">{formatDateTime(claim.expires_at)}에 사라집니다.</p>
    </div>
  );
}
