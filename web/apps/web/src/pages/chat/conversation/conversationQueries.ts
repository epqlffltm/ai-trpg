// web/apps/web/src/pages/chat/conversation/conversationQueries.ts
// 대화(C3)가 읽는 것. 대화 하나와 고를 수 있는 모델.
// 대화의 열쇠는 내 대화의 목록(['chat', 'conversations', …])과 다르게 둔다. 목록을 다시 읽을 때 이 대화까지 다시 읽지 않는다.
// 다른 곳(다른 탭, 끊긴 뒤)에서 답을 쓰는 중이면(generating) 끝날 때까지 3초마다 다시 읽는다. 이 화면이 받는 중이면 묻지 않는다.

import { queryOptions } from '@tanstack/react-query';
import { fetchChatModels, fetchConversation } from '../../../api/chatConversation';
import { isClientError } from '../../../api/http';

export const GENERATING_POLL_MS = 3000;

export function conversationKey(id: string) {
  return ['chat', 'conversation', id] as const;
}

export function conversationQuery(id: string, streaming: boolean) {
  return queryOptions({
    queryKey: conversationKey(id),
    queryFn: ({ signal }) => fetchConversation(id, signal),
    retry: (count, error) => !isClientError(error) && count < 2,
    refetchInterval: (query) => (query.state.data?.generating && !streaming ? GENERATING_POLL_MS : false),
  });
}

/** 모델의 값은 결제 서버의 가격표를 따라 바뀐다. 1분 동안은 다시 읽지 않는다 */
export function chatModelsQuery() {
  return queryOptions({
    queryKey: ['chat', 'models'],
    queryFn: ({ signal }) => fetchChatModels(signal),
    staleTime: 60 * 1000,
  });
}
