// web/apps/web/src/pages/attendance/AttendanceCycle.tsx
// 출석 주기의 칸들(A9). 하루마다 실버의 양, 마지막 칸은 보물 상자. 받은 날, 오늘, 앞으로를 칸의 모양으로 가른다.
// 양은 보상표(rewards)에서 읽는다. 칸의 상태는 attendanceView.ts 의 cycleCells.
// 모양은 Stitch 18번: 세로로 긴 칸, 가운데 동그란 표(받음 체크, 오늘 별, 앞으로 자물쇠, 마지막 날 상자). 오늘 칸은 보라빛, 상자 칸은 주황 테.

import { CheckIcon, ChestIcon, LockIcon, StarIcon } from '../../components/icons';
import type { CycleCell } from './attendanceView';
import { cellLabel } from './attendanceView';

export function AttendanceCycle({ cells }: { cells: CycleCell[] }) {
  return (
    <ol className="attendance-cycle" aria-label="출석 주기">
      {cells.map((cell) => (
        <li key={cell.day} className={`attendance-cell attendance-cell--${cell.state}`} aria-label={cellLabel(cell)} aria-current={cell.state === 'today' || cell.state === 'claimed' ? 'date' : undefined}>
          <span className="attendance-cell__day">{cell.day}일째</span>
          <span className="attendance-cell__icon" aria-hidden="true">
            <CellIcon cell={cell} />
          </span>
          <span className="attendance-cell__silver">실버 {cell.silver}</span>
        </li>
      ))}
    </ol>
  );
}

function CellIcon({ cell }: { cell: CycleCell }) {
  if (cell.chest) return <ChestIcon />;
  if (cell.state === 'done' || cell.state === 'claimed') return <CheckIcon />;
  if (cell.state === 'today') return <StarIcon />;
  return <LockIcon />;
}
