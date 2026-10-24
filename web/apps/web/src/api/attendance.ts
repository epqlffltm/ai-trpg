// web/apps/web/src/api/attendance.ts
// 출석과 보물 상자(결제 서버, A9). 오늘의 출석, 받기, 보상표.
//
// 실패(billing-server/README.md 의 "출석"):
//   - 403 attendance.verification_required: 본인인증 전이다
//   - 409 attendance.already_claimed: 오늘 이미 받았다. 한국 자정에 다시 받는다
//   - 503: 잠시 뒤 다시 부를 것이다(로그아웃시키지 않는다)
// 받기는 하루에 한 번이라 다시 보내도 두 번 받지 않는다(두 번째는 409). 그래서 열쇠(Idempotency-Key)를 붙이지 않는다.

import { apiRequest } from './http';
import type { AttendanceClaim, AttendanceRewards, AttendanceStatus } from './types';

const ATTENDANCE = '/api/v1/billing/attendance';

/** 오늘 받았는지, 주기의 며칠째인지, 오늘의 양, 상자를 여는 날인지, 본인인증을 마쳤는지 */
export function fetchAttendance(signal?: AbortSignal): Promise<AttendanceStatus> {
  return apiRequest<AttendanceStatus>(ATTENDANCE, signal ? { signal } : {});
}

/** 오늘의 보상을 받는다. 주기의 마지막 날이면 보물 상자의 결과가 함께 온다 */
export function claimAttendance(): Promise<AttendanceClaim> {
  return apiRequest<AttendanceClaim>(ATTENDANCE, { method: 'POST' });
}

/** 주기의 하루 양과 보물 상자의 확률표. 로그인 없이도 읽는다 */
export function fetchAttendanceRewards(signal?: AbortSignal): Promise<AttendanceRewards> {
  return apiRequest<AttendanceRewards>(`${ATTENDANCE}/rewards`, signal ? { signal } : {});
}
