// web/apps/web/src/pages/attendance/AttendanceCycle.tsx
// 출석 주기의 칸들(A9). 하루마다 실버의 양, 마지막 칸은 보물 상자. 받은 날, 오늘, 앞으로를 칸의 모양으로 가른다.
// 양은 보상표(rewards)에서 읽는다. 칸의 상태는 attendanceView.ts 의 cycleCells.

import type { CycleCell } from './attendanceView';
import { cellLabel } from './attendanceView';

export function AttendanceCycle({ cells }: { cells: CycleCell[] }) {
  return (
    <ol className="attendance-cycle" aria-label="출석 주기">
      {cells.map((cell) => (
        <li key={cell.day} className={`attendance-cell attendance-cell--${cell.state}`} aria-label={cellLabel(cell)} aria-current={cell.state === 'today' || cell.state === 'claimed' ? 'date' : undefined}>
          <span className="attendance-cell__day">{cell.day}일째</span>
          <span className="attendance-cell__icon" aria-hidden="true">
            {cell.chest ? '상자' : cell.state === 'done' || cell.state === 'claimed' ? '✓' : '·'}
          </span>
          <span className="attendance-cell__silver">실버 {cell.silver}</span>
        </li>
      ))}
    </ol>
  );
}
