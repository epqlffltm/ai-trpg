// web/apps/web/src/api/worlds.ts
// 게임 서버의 세계관(제작 도구 B9 의 재료 하나). 설정(setting)은 서술하는 AI 가 읽고, GM 메모(gm_notes)는 테이블에 앉은 사람에게 가지 않는다.
// 목록과 지우기는 재료가 함께 쓴다(studio.ts).

import { apiRequest } from './http';
import { assetPath, assetsPath } from './studio';
import type { WorldCreate, WorldDetail, WorldUpdate } from './types';

export function fetchWorld(worldId: string, signal?: AbortSignal): Promise<WorldDetail> {
  return apiRequest<WorldDetail>(assetPath('worlds', worldId), signal ? { signal } : {});
}

export function createWorld(body: WorldCreate): Promise<WorldDetail> {
  return apiRequest<WorldDetail>(assetsPath('worlds'), { method: 'POST', body });
}

/** 보낸 칸만 바뀐다. 이미 게시한 판은 게시할 때의 세계관으로 굳어 있다 */
export function updateWorld(worldId: string, body: WorldUpdate): Promise<WorldDetail> {
  return apiRequest<WorldDetail>(assetPath('worlds', worldId), { method: 'PATCH', body });
}
