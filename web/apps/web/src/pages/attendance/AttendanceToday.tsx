// web/apps/web/src/pages/attendance/AttendanceToday.tsx
// 오늘의 출석(A9): 주기의 칸, 오늘의 양, 받기와 받은 결과. 출석 화면(AttendancePage)과 마이페이지 내 포인트 탭(MyAttendance)이 함께 쓴다.
// 제목과 칸의 틀은 쓰는 쪽이 둔다. 받으면 새로 받은 활동 배지(#193)를 함께 적고 마이페이지의 배지로 가는 길을 둔다.
// 본인인증 전이면 받기를 막고 까닭을 적는다. 받은 실버는 30일 뒤에 사라지고 스탠다드 모델에만 쓴다.

import { Button, Notice } from '@ai-trpg/ui';
import { Link } from 'react-router';
import type { AttendanceClaim, AttendanceRewards, AttendanceStatus } from '../../api/attendance';
import { AttendanceCycle } from './AttendanceCycle';
import { VERIFY_FIRST } from './attendanceProblem';
import { badgesLine, chestLine, claimButtonLabel, claimLine, cycleCells, todayLine } from './attendanceView';
import { useClaimAttendance } from './useClaimAttendance';

export function AttendanceToday({ status, rewards }: { status: AttendanceStatus; rewards: AttendanceRewards }) {
  const claiming = useClaimAttendance();
  const blocked = !status.verified || status.claimed;
  return (
    <>
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
    </>
  );
}

function ClaimResult({ claim }: { claim: AttendanceClaim }) {
  const chest = chestLine(claim);
  const badges = badgesLine(claim);
  return (
    <div className="attendance-result" role="status">
      <p>{claimLine(claim)}</p>
      {chest ? <p className="attendance-result__chest">{chest}</p> : null}
      {badges ? (
        <p className="attendance-result__badges">
          {badges} · <Link to="/me?tab=settings">활동 배지 보기</Link>
        </p>
      ) : null}
      <p className="hint">실버는 몇 초 뒤 지갑에 들어갑니다. 지갑에 보이지 않으면 잠시 뒤 다시 열어 보세요.</p>
    </div>
  );
}
