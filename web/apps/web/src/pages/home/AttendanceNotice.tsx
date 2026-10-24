// web/apps/web/src/pages/home/AttendanceNotice.tsx
// 홈(A1)의 출석 알림. 로그인했고, 본인인증을 마쳤고, 오늘 아직 받지 않았으면 한 줄과 출석(A9)으로 가는 길을 보인다.
// 출석을 읽지 못했거나 읽는 중이면 아무것도 보이지 않는다(홈을 막지 않는다). 받으면 출석 화면이 오늘의 출석을 다시 읽어 사라진다.

import { Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { attendanceQuery } from '../attendance/attendanceQueries';
import { todayLine } from '../attendance/attendanceView';

export function AttendanceNotice() {
  const attendance = useQuery(attendanceQuery());
  const status = attendance.data;
  if (!status || !status.verified || status.claimed) return null;
  return (
    <Notice>
      오늘의 출석을 아직 받지 않았습니다. {todayLine(status)}. <Link to="/wallet/attendance">출석하러 가기</Link>
    </Notice>
  );
}
