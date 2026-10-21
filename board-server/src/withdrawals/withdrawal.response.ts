// board-server/src/withdrawals/withdrawal.response.ts

/**
 * 탈퇴를 받은 답. 인증 서버는 processed 를 받아야 보내기를 멈춘다.
 *
 * 응답의 모양은 클래스로 적는다. API 목록(docs/api/board.openapi.json)이 빌드할 때 클래스의 칸과 주석을 읽는다.
 */

/** 받은 결과. 늘 processed 다 */
export const WITHDRAWAL_PROCESSED = 'processed';

export class WithdrawalResponse {
  /** 반영했다. 이미 했거나 할 것이 없었던 것도 같다 */
  status: typeof WITHDRAWAL_PROCESSED;
}
