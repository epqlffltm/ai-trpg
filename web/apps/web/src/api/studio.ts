// web/apps/web/src/api/studio.ts
// 제작 도구(B9)의 재료가 함께 쓰는 부르기. 재료마다 주소의 이름만 다르고 목록과 지우기의 모양이 같다.
// 시나리오도 같은 주소의 모양이라 목록과 지우기를 함께 쓴다.
// 모두 만든 사람 자신의 것만 읽고 쓴다. 남의 것은 있어도 404 다. 쓰는 시나리오가 있으면 지우지 못한다(409 used_by).

import { apiRequest } from './http';
import type { AssetPage } from './types';

/** 재료의 종류. 게임 서버의 주소 /api/v1/game/<종류> 다 */
export type StudioKind = 'rulebooks' | 'worlds' | 'lorebooks' | 'bestiaries' | 'scenarios';

export function assetsPath(kind: StudioKind): string {
  return `/api/v1/game/${kind}`;
}

export function assetPath(kind: StudioKind, assetId: string): string {
  return `${assetsPath(kind)}/${encodeURIComponent(assetId)}`;
}

/** 내 재료의 한 쪽. 최근에 만든 것부터. 긴 글은 싣지 않는다 */
export function fetchAssets(kind: StudioKind, page: { limit: number; offset: number }, signal?: AbortSignal): Promise<AssetPage> {
  return apiRequest<AssetPage>(assetsPath(kind), { query: page, ...(signal ? { signal } : {}) });
}

/** 204. 쓰는 시나리오가 있으면 409(used_by) */
export function deleteAsset(kind: StudioKind, assetId: string): Promise<void> {
  return apiRequest<void>(assetPath(kind, assetId), { method: 'DELETE' });
}
