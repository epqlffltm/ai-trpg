// web/apps/web/src/api/tableSnapshots.ts
// 테이블의 장면 그림(#983). 앉은 사람 누구나 라운드의 장면을 그림 한 장으로 만들고, 누른 사람이 낸다.
//   - 그리기는 홀드를 건 뒤 202(그리는 중)로 바로 답한다. 다 그렸는지는 목록을 다시 읽어 안다(status 가 ready)
//   - 그림의 바이트는 asset 이 아니라 게임 서버가 대신 내준다(앉은 사람만). 토큰을 실어 받는다
//   - 누가 그렸든 앉은 사람 모두가 본다. 내가 그린 것만 by_me 가 참이고, 실패의 까닭(code)도 내 것에만 온다
//   - 한 장의 값은 GET /snapshots/price. available 이 거짓이면 그 서버에서는 그릴 수 없다(단추를 숨긴다)
// 실패: 402 credit_short·gold_required, 409 snapshot_in_progress(그 테이블에서 그리는 중), 422 not_drawable(장면이 없다),
//       503 snapshot_unavailable·billing_unavailable·asset_unavailable, 404(앉지 않은 테이블, 없는 라운드, snapshot_not_found)

import type { components as Trpg } from './generated/trpg';
import { apiBlob, apiRequest } from './http';

export type TableSnapshot = Trpg['schemas']['SnapshotOut'];
export type TableSnapshotPrice = Trpg['schemas']['SnapshotPriceOut'];

function tablePath(tableId: string, rest: string): string {
  return `/api/v1/game/tables/${encodeURIComponent(tableId)}${rest}`;
}

/** 그 테이블의 그림들(만든 차례) */
export function fetchTableSnapshots(tableId: string, signal?: AbortSignal): Promise<TableSnapshot[]> {
  return apiRequest<TableSnapshot[]>(tablePath(tableId, '/snapshots'), signal ? { signal } : {});
}

/** 그 라운드의 장면을 그리기 시작한다. 받은 것은 그리는 중(drawing)이다 */
export function drawTableSnapshot(tableId: string, roundNumber: number): Promise<TableSnapshot> {
  return apiRequest<TableSnapshot>(tablePath(tableId, `/rounds/${roundNumber}/snapshot`), { method: 'POST' });
}

/** 다 그린 그림의 바이트. 프록시 없이 부르면 빈 본문이다 */
export function fetchTableSnapshotImage(tableId: string, snapshotId: string, signal?: AbortSignal): Promise<Blob> {
  return apiBlob(tablePath(tableId, `/snapshots/${encodeURIComponent(snapshotId)}/image`), signal ? { signal } : {});
}

/** 장면 그림 한 장의 값과 그릴 수 있는지. 가격 목록을 받지 못하면 503 prices_unavailable */
export function fetchTableSnapshotPrice(signal?: AbortSignal): Promise<TableSnapshotPrice> {
  return apiRequest<TableSnapshotPrice>('/api/v1/game/snapshots/price', signal ? { signal } : {});
}
