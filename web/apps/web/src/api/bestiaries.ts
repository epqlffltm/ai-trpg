// web/apps/web/src/api/bestiaries.ts
// 게임 서버의 몬스터 모음과 그 몬스터(제작 도구 B9). 모음은 제목과 소개만 갖고, 몬스터를 100 마리까지 담는다.
// 몬스터의 숫자(시트, 공격)는 여기가 아니라 시나리오가 정한다. 목록과 지우기는 재료가 함께 쓴다(studio.ts).

import { apiRequest } from './http';
import { assetPath, assetsPath } from './studio';
import type { AssetSummary, BestiaryCreate, BestiaryUpdate, Monster, MonsterCreate, MonsterUpdate } from './types';

function monstersPath(bestiaryId: string): string {
  return `${assetPath('bestiaries', bestiaryId)}/monsters`;
}

export function fetchBestiary(bestiaryId: string, signal?: AbortSignal): Promise<AssetSummary> {
  return apiRequest<AssetSummary>(assetPath('bestiaries', bestiaryId), signal ? { signal } : {});
}

export function createBestiary(body: BestiaryCreate): Promise<AssetSummary> {
  return apiRequest<AssetSummary>(assetsPath('bestiaries'), { method: 'POST', body });
}

export function updateBestiary(bestiaryId: string, body: BestiaryUpdate): Promise<AssetSummary> {
  return apiRequest<AssetSummary>(assetPath('bestiaries', bestiaryId), { method: 'PATCH', body });
}

/** 몬스터 전부. 만든 차례다 */
export function fetchMonsters(bestiaryId: string, signal?: AbortSignal): Promise<Monster[]> {
  return apiRequest<Monster[]>(monstersPath(bestiaryId), signal ? { signal } : {});
}

/** 가득 찼으면 409 */
export function addMonster(bestiaryId: string, body: MonsterCreate): Promise<Monster> {
  return apiRequest<Monster>(monstersPath(bestiaryId), { method: 'POST', body });
}

export function updateMonster(bestiaryId: string, monsterId: string, body: MonsterUpdate): Promise<Monster> {
  return apiRequest<Monster>(`${monstersPath(bestiaryId)}/${encodeURIComponent(monsterId)}`, { method: 'PATCH', body });
}

export function deleteMonster(bestiaryId: string, monsterId: string): Promise<void> {
  return apiRequest<void>(`${monstersPath(bestiaryId)}/${encodeURIComponent(monsterId)}`, { method: 'DELETE' });
}
