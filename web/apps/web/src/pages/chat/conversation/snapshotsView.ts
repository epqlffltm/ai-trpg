// web/apps/web/src/pages/chat/conversation/snapshotsView.ts
// 장면 그림(#983)의 글과 고르기. chat 의 대화와 story 의 장면이 함께 쓴다. 순수한 함수다.

import { ApiError } from '../../../api/errors';
import type { Snapshot } from '../../../api/snapshots';

/** 그리는 중인 것이 있으면 목록을 이만큼마다 다시 읽는다(ms) */
export const SNAPSHOT_POLL_MS = 3000;

/** 그 대화에 그리는 중인 그림이 있는가. 있으면 새로 그리지 못한다(서버도 409) */
export function isDrawing(snapshots: readonly Snapshot[]): boolean {
  return snapshots.some((snapshot) => snapshot.status === 'drawing');
}

/** 그 말의 그림들(만든 차례). 실패한 것은 끝의 것만 남긴다(다시 그렸으면 지난 실패는 보이지 않는다) */
export function snapshotsOf(snapshots: readonly Snapshot[], messageId: string): Snapshot[] {
  const mine = snapshots.filter((snapshot) => snapshot.message_id === messageId);
  const last = mine.at(-1);
  return mine.filter((snapshot) => snapshot.status !== 'failed' || snapshot === last);
}

/** 실패로 남은 그림의 까닭 */
export function snapshotFailureText(code: string | null): string {
  if (code === 'credit_short') return '크레딧이 모자라 그리지 못했습니다.';
  if (code === 'gold_required') return '장면 그림은 골드로만 만들 수 있습니다.';
  if (code === 'refused') return '안전 규칙에 걸려 그리지 못했습니다. 크레딧은 돌려드렸습니다.';
  return '그림을 만들지 못했습니다. 크레딧은 돌려드렸습니다.';
}

/** 그리기를 시작하지 못한 까닭 */
export function snapshotProblemText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'credit_short') return '크레딧이 모자랍니다. 충전한 뒤 다시 해 주세요.';
    if (error.code === 'gold_required') return '장면 그림은 골드로만 만들 수 있습니다.';
    if (error.code === 'snapshot_in_progress') return '이 대화에서 다른 그림을 그리는 중입니다. 끝나면 다시 해 주세요.';
    if (error.code === 'not_drawable') return '캐릭터의 답만 그림으로 만들 수 있습니다.';
    if (error.code === 'snapshot_unavailable') return '지금은 장면 그림을 만들 수 없습니다.';
    if (error.status === 429) return '너무 자주 요청했습니다. 잠시 뒤에 다시 해 주세요.';
  }
  return '장면 그림을 시작하지 못했습니다. 잠시 뒤에 다시 해 주세요.';
}
