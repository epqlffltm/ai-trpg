// web/apps/web/src/api/portraits.ts
// TRPG 의 캐릭터 그림(#983). 시나리오 제작자가 프리젠에 붙이는 그림이다(플레이어 캐릭터에는 받지 않는다).
//   - 올리기는 게임 서버로 그림 파일의 바이트를 그대로 보낸다(multipart 가 아니다). 게임 서버가 asset 에 맡긴다
//   - 내 그림의 목록과 바이트, 지우기는 게임 서버의 /portraits 다. 바이트는 토큰을 실어 받는다
//   - 지우기는 어느 초안이나 판에도 붙지 않은 그림만 된다. 붙어 있으면 409 portrait_in_use 와 쓰는 시나리오들(scenarios)
// 실패: 413 image_too_large, 415 image_format, 422 image_unreadable, 409 portrait_limit(100장), 503 asset_unavailable,
//       404 portrait_not_found

import type { components as Trpg } from './generated/trpg';
import { apiBlob, apiRequest } from './http';

export type Portrait = Trpg['schemas']['PortraitOut'];
export type PortraitPage = Trpg['schemas']['PortraitPage'];

/** 그림을 고르는 창이 한 번에 읽는 수 */
export const PORTRAIT_PAGE_SIZE = 20;

const PORTRAITS = '/api/v1/game/portraits';

export function uploadPortrait(file: Blob): Promise<Portrait> {
  return apiRequest<Portrait>(PORTRAITS, { method: 'POST', file });
}

/** 내가 올린 그림들의 한 쪽. 최근 것부터 */
export function fetchPortraits(offset: number, signal?: AbortSignal): Promise<PortraitPage> {
  return apiRequest<PortraitPage>(PORTRAITS, { query: { limit: PORTRAIT_PAGE_SIZE, offset }, ...(signal ? { signal } : {}) });
}

/** 내가 올린 그림의 바이트 */
export function fetchPortraitImage(portraitId: string, signal?: AbortSignal): Promise<Blob> {
  return apiBlob(`${PORTRAITS}/${encodeURIComponent(portraitId)}/image`, signal ? { signal } : {});
}

export function deletePortrait(portraitId: string): Promise<void> {
  return apiRequest<void>(`${PORTRAITS}/${encodeURIComponent(portraitId)}`, { method: 'DELETE' });
}
