// web/apps/web/src/pages/trpg/room/snapshots/tableSnapshotsView.ts
// 테이블의 장면 그림(#983)의 글과 고르기. 순수한 함수다.
// 단추의 글과 설명, 실패의 까닭은 chat·story 의 것(pages/chat/conversation/snapshotsView.ts)을 그대로 쓰고,
// 테이블에만 있는 것(라운드마다 고르기, 남의 그림, 시작하지 못한 까닭)만 여기에 둔다.

import { ApiError } from '../../../../api/errors';
import type { TableSnapshot } from '../../../../api/tableSnapshots';

/** 그 테이블에 그리는 중인 그림이 있는가. 있으면 새로 그리지 못한다(서버도 409) */
export function isTableDrawing(snapshots: readonly TableSnapshot[]): boolean {
  return snapshots.some((snapshot) => snapshot.status === 'drawing');
}

/**
 * 그 라운드의 그림들(만든 차례). 남의 실패는 보이지 않는다(까닭은 그린 사람의 일이다).
 * 내 실패는 끝의 것만 남긴다(다시 그렸으면 지난 실패는 숨긴다)
 */
export function snapshotsOfRound(snapshots: readonly TableSnapshot[], roundNumber: number): TableSnapshot[] {
  const shown = snapshots.filter(
    (snapshot) => snapshot.round_number === roundNumber && (snapshot.status !== 'failed' || snapshot.by_me),
  );
  const last = shown.at(-1);
  return shown.filter((snapshot) => snapshot.status !== 'failed' || snapshot === last);
}

/** 그림 아래에 적는 것. 내가 그린 것이면 그렇게 적는다(서버는 누가 그렸는지 by_me 만 준다) */
export function snapshotCaption(snapshot: TableSnapshot): string {
  return snapshot.by_me ? 'AI 가 만든 그림 · 내가 그림' : 'AI 가 만든 그림';
}

/** 저장할 때의 파일 이름. "장면그림-라운드3-1a2b3c4d.png". 모르는 형식이면 png 로 둔다 */
export function tableSnapshotFileName(snapshot: TableSnapshot, mimeType: string): string {
  const extension = { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp' }[mimeType] ?? 'png';
  return `장면그림-라운드${snapshot.round_number}-${snapshot.id.slice(0, 8)}.${extension}`;
}

/** 그리기를 시작하지 못한 까닭 */
export function tableSnapshotProblemText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'credit_short') return '크레딧이 모자랍니다. 충전한 뒤 다시 해 주세요.';
    if (error.code === 'gold_required') return '장면 그림은 골드로만 만들 수 있습니다.';
    if (error.code === 'snapshot_in_progress') return '이 테이블에서 다른 그림을 그리는 중입니다. 끝나면 다시 해 주세요.';
    if (error.code === 'not_drawable') return '장면이 있는 라운드만 그림으로 만들 수 있습니다.';
    if (error.code === 'snapshot_unavailable') return '지금은 장면 그림을 만들 수 없습니다.';
    if (error.status === 404) return '라운드를 찾지 못했습니다. 테이블을 다시 읽습니다.';
    if (error.status === 429) return '너무 자주 요청했습니다. 잠시 뒤에 다시 해 주세요.';
  }
  return '장면 그림을 시작하지 못했습니다. 잠시 뒤에 다시 해 주세요.';
}

/** 그림을 지우지 못한 까닭 */
export function tableSnapshotDeleteProblemText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'snapshot_not_found') return '이미 지웠거나 찾을 수 없는 그림입니다.';
    if (error.code === 'snapshot_in_progress') return '아직 그리는 중이라 지울 수 없습니다.';
    if (error.code === 'snapshot_settling') return '청구를 정리하는 중입니다. 잠시 뒤에 다시 해 주세요.';
    if (error.code === 'asset_unavailable') return '지금은 그림을 지울 수 없습니다. 잠시 뒤에 다시 해 주세요.';
    if (error.status === 429) return '너무 자주 요청했습니다. 잠시 뒤에 다시 해 주세요.';
  }
  return '그림을 지우지 못했습니다. 잠시 뒤에 다시 해 주세요.';
}
