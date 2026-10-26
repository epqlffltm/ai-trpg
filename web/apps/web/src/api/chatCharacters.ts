// web/apps/web/src/api/chatCharacters.ts
// chat 의 캐릭터 탐색(C1)과 소개(C2)가 부르는 것. 공개 캐릭터는 asset 서버, 내 대화와 연 장면은 chat 서버가 준다(#593).
//
// 공개 목록은 최근에 게시한 것부터, 마지막 판의 값이다. 로그인하지 않으면 전체이용가만 오고, 성인 등급은 성인 확인을 한 사람에게만 온다.
// 대화를 시작하면(POST /chat/conversations) chat 서버가 asset 서버에서 그 캐릭터의 마지막 판을 가져와 고정한다.
// 시작의 실패(chat-server/README.md 의 "대화"):
//   - 404 character_not_found: 없다, 공개가 내려갔다, 볼 수 없는 등급
//   - 403 adult_content_required: 자기 캐릭터인데 등급을 쓸 수 없다
//   - 422 start_not_found: 고른 시작 상황이 마지막 판에 없다(그사이에 새 판이 나왔다)
//   - 503 asset_unavailable, prices_unavailable: 다른 서버에 닿지 못했다. Retry-After 가 붙는다

import { apiRequest } from './http';
import type { ChatUnlockPage, ConversationCreate, ConversationDetail, ConversationPage, PublicCharacterPage } from './types';

/** 탐색의 한 쪽 */
export const CHARACTER_PAGE_SIZE = 20;
/** 소개의 "이 캐릭터와의 대화"의 한 쪽 */
export const CONVERSATION_PAGE_SIZE = 20;
/** 한 캐릭터의 연 장면을 한 번에 읽는 수(서버의 최대). 한 캐릭터의 씬은 이보다 적다 */
const UNLOCK_LIMIT = 100;

export function fetchPublicCharacterPage(offset: number, signal?: AbortSignal): Promise<PublicCharacterPage> {
  return apiRequest<PublicCharacterPage>('/api/v1/asset/listings/characters', { query: { limit: CHARACTER_PAGE_SIZE, offset }, ...withSignal(signal) });
}

/** 이 캐릭터(asset 의 id)와의 내 대화. 최근에 말한 것부터 */
export function fetchConversationsWith(characterId: string, offset: number, signal?: AbortSignal): Promise<ConversationPage> {
  return apiRequest<ConversationPage>('/api/v1/chat/conversations', {
    query: { character_id: characterId, limit: CONVERSATION_PAGE_SIZE, offset },
    ...withSignal(signal),
  });
}

/** 이 캐릭터에서 내가 연 장면 */
export function fetchUnlocksOf(characterId: string, signal?: AbortSignal): Promise<ChatUnlockPage> {
  return apiRequest<ChatUnlockPage>('/api/v1/chat/gallery', { query: { character_id: characterId, limit: UNLOCK_LIMIT }, ...withSignal(signal) });
}

/**
 * 대화를 시작한다. 모델은 보내지 않는다(서버가 지난번 것을 쓴다).
 * 페르소나는 고른 것(id), 없이(null), 보내지 않음(서버가 지난번 대화의 것을 쓴다) 가운데 하나다. 남의 것이면 404 persona_not_found
 */
export function startConversation(body: Pick<ConversationCreate, 'character_id' | 'start' | 'persona_id'>): Promise<ConversationDetail> {
  return apiRequest<ConversationDetail>('/api/v1/chat/conversations', { method: 'POST', body });
}

function withSignal(signal: AbortSignal | undefined): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}
