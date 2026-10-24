// web/apps/web/src/pages/attendance/attendanceQueries.ts
// 출석(A9)이 읽는 것의 열쇠. 결제 서버의 열쇠(billing) 아래에 둔다. 받으면 오늘의 출석과 잔액을 다시 읽는다.
// 보상표는 서버가 표의 판을 올릴 때만 바뀌므로 한 시간 동안 다시 읽지 않는다.

import { queryOptions } from '@tanstack/react-query';
import { fetchAttendance, fetchAttendanceRewards } from '../../api/attendance';

const HOUR_MS = 60 * 60 * 1000;

export const ATTENDANCE_KEY = ['billing', 'attendance'] as const;

export function attendanceQuery() {
  return queryOptions({
    queryKey: [...ATTENDANCE_KEY, 'today'],
    queryFn: ({ signal }) => fetchAttendance(signal),
    refetchOnWindowFocus: true,
  });
}

export function rewardsQuery() {
  return queryOptions({
    queryKey: [...ATTENDANCE_KEY, 'rewards'],
    queryFn: ({ signal }) => fetchAttendanceRewards(signal),
    staleTime: HOUR_MS,
  });
}
