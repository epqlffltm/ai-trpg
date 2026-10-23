// web/apps/web/src/api/lorebooks.ts
// 게임 서버의 로어북과 그 항목(제작 도구 B9). 로어북은 제목과 소개만 갖고, 항목(인물, 장소, 물건 …)을 100 개까지 담는다.
// 항목은 서술하는 AI 가 키워드로 찾아 읽는 설정이다. 목록과 지우기는 재료가 함께 쓴다(studio.ts).

import { apiRequest } from './http';
import { assetPath, assetsPath } from './studio';
import type { AssetSummary, LorebookCreate, LorebookUpdate, LoreEntry, LoreEntryCreate, LoreEntryUpdate } from './types';

function entriesPath(lorebookId: string): string {
  return `${assetPath('lorebooks', lorebookId)}/entries`;
}

export function fetchLorebook(lorebookId: string, signal?: AbortSignal): Promise<AssetSummary> {
  return apiRequest<AssetSummary>(assetPath('lorebooks', lorebookId), signal ? { signal } : {});
}

export function createLorebook(body: LorebookCreate): Promise<AssetSummary> {
  return apiRequest<AssetSummary>(assetsPath('lorebooks'), { method: 'POST', body });
}

export function updateLorebook(lorebookId: string, body: LorebookUpdate): Promise<AssetSummary> {
  return apiRequest<AssetSummary>(assetPath('lorebooks', lorebookId), { method: 'PATCH', body });
}

/** 항목 전부. 만든 차례다 */
export function fetchEntries(lorebookId: string, signal?: AbortSignal): Promise<LoreEntry[]> {
  return apiRequest<LoreEntry[]>(entriesPath(lorebookId), signal ? { signal } : {});
}

/** 가득 찼으면 409 */
export function addEntry(lorebookId: string, body: LoreEntryCreate): Promise<LoreEntry> {
  return apiRequest<LoreEntry>(entriesPath(lorebookId), { method: 'POST', body });
}

export function updateEntry(lorebookId: string, entryId: string, body: LoreEntryUpdate): Promise<LoreEntry> {
  return apiRequest<LoreEntry>(`${entriesPath(lorebookId)}/${encodeURIComponent(entryId)}`, { method: 'PATCH', body });
}

export function deleteEntry(lorebookId: string, entryId: string): Promise<void> {
  return apiRequest<void>(`${entriesPath(lorebookId)}/${encodeURIComponent(entryId)}`, { method: 'DELETE' });
}
