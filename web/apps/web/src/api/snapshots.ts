// web/apps/web/src/api/snapshots.ts
// 장면 그림(#983). chat 의 대화와 story 의 세션이 같은 모양이다. 캐릭터의 답 하나를 그림 한 장으로 만든다.
//   - 그리기는 홀드를 건 뒤 202(그리는 중)로 바로 답한다. 그림은 목록을 다시 읽어 받는다(ready 이면 image_id 가 있다)
//   - 그림의 바이트는 asset 의 그림 주소로 토큰을 실어 받는다(api/images.ts 의 fetchImage)
//   - 실패한 것(공급자의 거절, 서버의 오류)은 failed 와 까닭(code)으로 남고 크레딧은 돌려준다
//   - 한 장의 값은 따로 받는다(GET /snapshots/price). available 이 거짓이면 그 서버에서는 그릴 수 없다(단추를 숨긴다)
//   - 내 다 그린 그림들(갤러리)은 GET /snapshots 로 쪽마다 받는다. 최근에 만든 것부터, 지운 대화의 것은 없다
// 실패: 402 credit_short·gold_required, 409 snapshot_in_progress(그 대화에서 그리는 중), 422 not_drawable(캐릭터의 답이 아니다),
//       503 snapshot_unavailable(그리지 않는 서버이거나 팔지 않는다), 404(남의 대화)

import type { components as Chat } from './generated/chat';
import type { components as Story } from './generated/story';
import { apiRequest } from './http';

export type SnapshotService = 'chat' | 'story';
export type Snapshot = Chat['schemas']['SnapshotOut'] | Story['schemas']['SnapshotOut'];
export type SnapshotPrice = Chat['schemas']['SnapshotPriceOut'] | Story['schemas']['SnapshotPriceOut'];
export type KeptSnapshot = Chat['schemas']['KeptSnapshotOut'] | Story['schemas']['KeptSnapshotOut'];
export type KeptSnapshotPage = Chat['schemas']['KeptSnapshotPage'] | Story['schemas']['KeptSnapshotPage'];

/** 갤러리가 한 번에 읽는 그림 수 */
export const KEPT_PAGE_SIZE = 24;

export function fetchSnapshots(service: SnapshotService, conversationId: string, signal?: AbortSignal): Promise<Snapshot[]> {
  const path = `/api/v1/${service}/conversations/${encodeURIComponent(conversationId)}/snapshots`;
  return apiRequest<Snapshot[]>(path, signal ? { signal } : {});
}

/** 그 답을 그리기 시작한다. 받은 것은 그리는 중(drawing)이다 */
export function drawSnapshot(service: SnapshotService, messageId: string): Promise<Snapshot> {
  return apiRequest<Snapshot>(`/api/v1/${service}/messages/${encodeURIComponent(messageId)}/snapshot`, { method: 'POST' });
}

/** 장면 그림 한 장의 값과 그릴 수 있는지. 가격 목록을 받지 못하면 503 prices_unavailable */
export function fetchSnapshotPrice(service: SnapshotService, signal?: AbortSignal): Promise<SnapshotPrice> {
  return apiRequest<SnapshotPrice>(`/api/v1/${service}/snapshots/price`, signal ? { signal } : {});
}

/** 내 다 그린 그림들의 한 쪽. offset 부터 KEPT_PAGE_SIZE 장 */
export function fetchKeptSnapshots(service: SnapshotService, offset: number, signal?: AbortSignal): Promise<KeptSnapshotPage> {
  return apiRequest<KeptSnapshotPage>(`/api/v1/${service}/snapshots`, { query: { limit: KEPT_PAGE_SIZE, offset }, ...(signal ? { signal } : {}) });
}
