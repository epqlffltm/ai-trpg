// web/apps/web/src/api/lists.ts
// 첫 화면(A1)이 부르는 목록들. 서비스마다 그 서버를 따로 부르고 화면이 놓는다(#593).
// 모아 주는 서버를 두지 않는다. 한 서버가 답하지 않으면 그 줄만 빈다.
// 공개 목록은 로그인하지 않아도 부른다. 그때는 토큰이 없어 Authorization 을 보내지 않고, 전체이용가만 온다(#530).

import { apiRequest } from './http';
import type { ConversationPage, PublicCharacterPage, PublicListingPage, TablePage } from './types';

/** TRPG 의 공개 시나리오. 최근 공개한 것부터 */
export function fetchPublicScenarios(limit: number, signal?: AbortSignal): Promise<PublicListingPage> {
  return apiRequest<PublicListingPage>('/api/v1/game/listings', { query: { limit }, ...withSignal(signal) });
}

/** 내가 앉아 있는 테이블. 로그인한 사람만 */
export function fetchMyTables(limit: number, signal?: AbortSignal): Promise<TablePage> {
  return apiRequest<TablePage>('/api/v1/game/tables', { query: { limit }, ...withSignal(signal) });
}

/** chat 의 공개 캐릭터 */
export function fetchPublicCharacters(limit: number, signal?: AbortSignal): Promise<PublicCharacterPage> {
  return apiRequest<PublicCharacterPage>('/api/v1/asset/listings/characters', {
    query: { limit },
    ...withSignal(signal),
  });
}

/** 내 chat 대화. 서버가 준 차례(최근 것부터) 그대로. 로그인한 사람만 */
export function fetchMyConversations(limit: number, signal?: AbortSignal): Promise<ConversationPage> {
  return apiRequest<ConversationPage>('/api/v1/chat/conversations', { query: { limit }, ...withSignal(signal) });
}

function withSignal(signal: AbortSignal | undefined): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}
