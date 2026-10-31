// web/apps/web/src/api/characters.ts
// asset 서버의 캐릭터(chat 의 캐릭터 만들기 C6). 모두 만든 사람 자신의 것만 읽고 쓴다. 남의 것은 있어도 404 다.
// 지금(1~2단계)은 운영자만 만든다. 아니면 403 operator_only. 공개로 두는 것도 운영자만이다(PUBLIC_FOR_EVERYONE 을 켜기 전).
// 고치기는 초안만 바꾼다. 게시하면 지금의 초안이 새 판으로 굳고, 대화는 판을 복사해 간다.

import { apiRequest } from './http';
import type {
  AssetCharacterCreate,
  AssetCharacterDetail,
  AssetCharacterPage,
  AssetCharacterUpdate,
  AssetPublishCheck,
  AssetPublishResult,
  AssetVersionSummary,
} from './types';

const CHARACTERS = '/api/v1/asset/characters';

function characterPath(characterId: string): string {
  return `${CHARACTERS}/${characterId}`;
}

function withSignal(signal?: AbortSignal) {
  return signal ? { signal } : {};
}

/** 내 캐릭터 한 쪽. 최근에 고친 것부터 */
export function fetchMyCharacters(paging: { limit: number; offset: number }, signal?: AbortSignal): Promise<AssetCharacterPage> {
  return apiRequest<AssetCharacterPage>(CHARACTERS, { query: paging, ...withSignal(signal) });
}

/** 만들 때 보내는 것. 이름과 장르(반드시 하나). 나머지 칸은 서버가 기본으로 채운다(전체 이용가, 빈 칸들). 처음에는 비공개다 */
export type CharacterCreateBody = Pick<AssetCharacterCreate, 'name' | 'genre'>;

export function createCharacter(body: CharacterCreateBody): Promise<AssetCharacterDetail> {
  return apiRequest<AssetCharacterDetail>(CHARACTERS, { method: 'POST', body });
}

export function fetchCharacter(characterId: string, signal?: AbortSignal): Promise<AssetCharacterDetail> {
  return apiRequest<AssetCharacterDetail>(characterPath(characterId), withSignal(signal));
}

/** 보낸 칸만 바뀐다. 게시한 판은 그대로다 */
export function updateCharacter(characterId: string, body: AssetCharacterUpdate): Promise<AssetCharacterDetail> {
  return apiRequest<AssetCharacterDetail>(characterPath(characterId), { method: 'PATCH', body });
}

/** 지운다. 이미 시작한 남의 대화는 사본으로 돈다 */
export function deleteCharacter(characterId: string): Promise<void> {
  return apiRequest<void>(characterPath(characterId), { method: 'DELETE' });
}

/** 지금 게시하면 막히는 것(problems)과 소개에서 걸러질 것(removed). 판을 만들지 않는다 */
export function fetchCharacterCheck(characterId: string, signal?: AbortSignal): Promise<AssetPublishCheck> {
  return apiRequest<AssetPublishCheck>(`${characterPath(characterId)}/publish-check`, withSignal(signal));
}

export function fetchCharacterVersions(characterId: string, signal?: AbortSignal): Promise<AssetVersionSummary[]> {
  return apiRequest<AssetVersionSummary[]>(`${characterPath(characterId)}/versions`, withSignal(signal));
}

/** 지금 저장된 초안을 새 판으로 굳힌다. 막히면 409 problems */
export function publishCharacter(characterId: string, note: string): Promise<AssetPublishResult> {
  return apiRequest<AssetPublishResult>(`${characterPath(characterId)}/versions`, { method: 'POST', body: { note } });
}
