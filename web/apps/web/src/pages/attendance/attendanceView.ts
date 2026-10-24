// web/apps/web/src/pages/attendance/attendanceView.ts
// 출석(A9)이 보일 글과 칸. 순수한 함수다. 양은 결제 서버가 준 글자("140")를 그대로 쓰고, 하루 양은 보상표에서 읽는다(숫자를 박지 않는다).
// cycle_day 는 받았으면 받은 날의 차례, 아직이면 지금 받으면 될 차례다. 하루라도 빠지면 서버가 1 로 준다.

import type { AttendanceClaim, AttendanceRewards, AttendanceStatus } from '../../api/types';

/** 칸의 상태. 받음(이번 주기에 지난날), 오늘 받음, 오늘(아직), 앞으로 */
export type CellState = 'done' | 'claimed' | 'today' | 'later';

export type CycleCell = { day: number; silver: string; chest: boolean; state: CellState };

/** 주기의 칸들. 보상표의 하루 양과 오늘의 출석을 맞춘다 */
export function cycleCells(cycle: AttendanceRewards['cycle'], status: AttendanceStatus): CycleCell[] {
  return cycle.map((entry) => ({ day: entry.day, silver: entry.silver, chest: entry.chest, state: cellState(entry.day, status) }));
}

function cellState(day: number, status: AttendanceStatus): CellState {
  if (day < status.cycle_day) return 'done';
  if (day > status.cycle_day) return 'later';
  return status.claimed ? 'claimed' : 'today';
}

/** 칸의 읽히는 이름. "3일째, 실버 180, 오늘" */
export function cellLabel(cell: CycleCell): string {
  const parts = [`${cell.day}일째`, `실버 ${cell.silver}`];
  if (cell.chest) parts.push('보물 상자');
  parts.push(STATE_LABELS[cell.state]);
  return parts.join(', ');
}

const STATE_LABELS: Record<CellState, string> = { done: '받음', claimed: '오늘 받음', today: '오늘', later: '앞으로' };

/** 오늘의 한 줄. "오늘은 3일째 · 실버 180", 상자를 여는 날이면 "· 보물 상자를 엽니다" */
export function todayLine(status: AttendanceStatus): string {
  const head = `오늘은 ${status.cycle_day}일째 · 실버 ${status.silver}`;
  if (status.claimed) return `${head} · 받았습니다. 내일 다시 오세요.`;
  return status.chest ? `${head} · 보물 상자를 엽니다` : head;
}

/** 받기 단추의 글. 받았으면 "오늘은 받았습니다"(막힌다), 상자를 여는 날이면 "출석하고 상자 열기" */
export function claimButtonLabel(status: AttendanceStatus): string {
  if (status.claimed) return '오늘은 받았습니다';
  return status.chest ? '출석하고 상자 열기' : '출석하기';
}

/** 받은 것의 한 줄. "실버 180을 받았습니다" 대신 조사를 고르지 않게 "받음: 실버 180" */
export function claimLine(claim: AttendanceClaim): string {
  return `받음: 실버 ${claim.silver} (${claim.cycle_day}일째)`;
}

/** 보물 상자의 한 줄. "보물 상자: 고블린의 주머니 · 실버 300 (확률표 v1)". 상자가 없으면 null */
export function chestLine(claim: AttendanceClaim): string | null {
  if (!claim.chest) return null;
  return `보물 상자: ${claim.chest.name} · 실버 ${claim.chest.silver} (확률표 ${claim.chest.table})`;
}
