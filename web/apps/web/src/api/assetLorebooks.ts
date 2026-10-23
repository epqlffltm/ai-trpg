// web/apps/web/src/api/assetLorebooks.ts
// asset 서버의 로어북(chat 의 캐릭터가 붙이는 설정의 모음, #672). 모두 만든 사람 자신의 것만 읽고 쓴다. 남의 것은 있어도 404 다.
// 지금(1~2단계)은 운영자만 만든다. 아니면 403 operator_only. TRPG 의 로어북(api/lorebooks.ts, trpg 서버)과는 다른 것이다.
// 고치기는 초안만 바꾼다(항목은 목록을 통째로 바꾼다). 게시하면 지금의 초안이 새 판으로 굳고, 캐릭터는 게시할 때 그 마지막 판을 복사해 간다.

import { apiRequest } from './http';
import type {
  AssetLorebookCreate,
  AssetLorebookDetail,
  AssetLorebookPage,
  AssetLorebookUpdate,
  AssetLorebookVersionDetail,
  AssetLorebookVersionSummary,
} from './types';

const LOREBOOKS = '/api/v1/asset/lorebooks';

function lorebookPath(lorebookId: string): string {
  return `${LOREBOOKS}/${lorebookId}`;
}

function withSignal(signal?: AbortSignal) {
  return signal ? { signal } : {};
}

/** 내 로어북 한 쪽. 최근에 고친 것부터. limit 은 100 까지다 */
export function fetchMyLorebooks(paging: { limit: number; offset: number }, signal?: AbortSignal): Promise<AssetLorebookPage> {
  return apiRequest<AssetLorebookPage>(LOREBOOKS, { query: paging, ...withSignal(signal) });
}

/** 만들 때 보내는 것. 설명과 항목은 서버가 비워 둔다 */
export type LorebookCreateBody = Pick<AssetLorebookCreate, 'name'>;

export function createLorebook(body: LorebookCreateBody): Promise<AssetLorebookDetail> {
  return apiRequest<AssetLorebookDetail>(LOREBOOKS, { method: 'POST', body });
}

export function fetchLorebook(lorebookId: string, signal?: AbortSignal): Promise<AssetLorebookDetail> {
  return apiRequest<AssetLorebookDetail>(lorebookPath(lorebookId), withSignal(signal));
}

/** 보낸 칸만 바뀐다. 항목은 목록을 통째로 바꾼다. 게시한 판은 그대로다 */
export function updateLorebook(lorebookId: string, body: AssetLorebookUpdate): Promise<AssetLorebookDetail> {
  return apiRequest<AssetLorebookDetail>(lorebookPath(lorebookId), { method: 'PATCH', body });
}

/** 지운다. 판도 함께 지워진다. 이미 게시한 캐릭터의 판에 복사된 것은 남는다 */
export function deleteLorebook(lorebookId: string): Promise<void> {
  return apiRequest<void>(lorebookPath(lorebookId), { method: 'DELETE' });
}

export function fetchLorebookVersions(lorebookId: string, signal?: AbortSignal): Promise<AssetLorebookVersionSummary[]> {
  return apiRequest<AssetLorebookVersionSummary[]>(`${lorebookPath(lorebookId)}/versions`, withSignal(signal));
}

/** 지금 저장된 초안을 새 판으로 굳힌다. 막는 것은 없다(항목이 없어도 된다) */
export function publishLorebook(lorebookId: string, note: string): Promise<AssetLorebookVersionDetail> {
  return apiRequest<AssetLorebookVersionDetail>(`${lorebookPath(lorebookId)}/versions`, { method: 'POST', body: { note } });
}
