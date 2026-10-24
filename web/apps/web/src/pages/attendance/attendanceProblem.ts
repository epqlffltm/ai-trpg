// web/apps/web/src/pages/attendance/attendanceProblem.ts
// 출석을 읽거나 받지 못한 까닭을 화면의 한 줄로. 순수한 함수다.
// 403 attendance.verification_required(본인인증 전), 409 attendance.already_claimed(오늘 이미 받음), 503(잠시 뒤)

import { ApiError, NetworkError } from '../../api/errors';

export const VERIFY_FIRST = '본인인증을 마친 계정만 출석 보상을 받습니다. 본인인증 화면은 준비 중입니다.';
const ALREADY = '오늘은 이미 받았습니다. 한국 시각 자정이 지나면 다시 받습니다.';

/** 받기의 실패. alreadyClaimed 면 화면이 오늘의 출석을 다시 읽어 단추를 막는다 */
export function describeClaimProblem(error: unknown): { message: string; alreadyClaimed: boolean } {
  if (error instanceof ApiError && error.status === 409) return { message: ALREADY, alreadyClaimed: true };
  if (error instanceof ApiError && error.status === 403) return { message: VERIFY_FIRST, alreadyClaimed: false };
  return { message: attendanceProblemText(error), alreadyClaimed: false };
}

/** 읽기의 실패 */
export function attendanceProblemText(error: unknown): string {
  if (error instanceof NetworkError) return '서버에 닿지 못했습니다. 연결을 확인하고 다시 시도하세요. 다시 받아도 두 번 받지 않습니다.';
  if (error instanceof ApiError && error.status === 503) {
    const after = error.retryAfter ? ` ${error.retryAfter}초 뒤에` : ' 잠시 뒤에';
    return `결제 서버가 지금 답하지 못합니다.${after} 다시 시도하세요.`;
  }
  return '출석을 처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';
}
