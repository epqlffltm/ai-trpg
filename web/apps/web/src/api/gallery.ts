// web/apps/web/src/api/gallery.ts
// 갤러리(C7). chat 서버의 연 이벤트 씬(`/chat/gallery`, 최근에 연 것부터)과, 그 씬의 그림과 이름이 있는 asset 의 공개 캐릭터 판.
// 연 기록은 사람, 캐릭터, 씬마다 한 줄이고 처음 연 때가 남는다. 판에서 해금 대상(collectible)인 씬만 갤러리의 칸이 된다.
// 공개를 내렸거나 숨긴 캐릭터는 판을 읽지 못한다(404). 그때는 연 수만 보인다.

import { apiRequest } from './http';
import type { ChatUnlockPage, PublicCharacterDetail } from './types';

/** 한 번에 읽는 연 기록 수(서버의 최대) */
export const UNLOCK_PAGE_SIZE = 100;

export function fetchChatUnlocks(offset: number, signal?: AbortSignal): Promise<ChatUnlockPage> {
  return apiRequest<ChatUnlockPage>('/api/v1/chat/gallery', { query: { limit: UNLOCK_PAGE_SIZE, offset }, ...(signal ? { signal } : {}) });
}

export function fetchPublicCharacter(id: string, signal?: AbortSignal): Promise<PublicCharacterDetail> {
  return apiRequest<PublicCharacterDetail>(`/api/v1/asset/listings/characters/${encodeURIComponent(id)}`, signal ? { signal } : {});
}
