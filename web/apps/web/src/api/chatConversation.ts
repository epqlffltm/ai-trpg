// web/apps/web/src/api/chatConversation.ts
// chat 의 대화 하나(C3). 읽기, 모델 고르기, 대안 고르기, 멈추기, 그리고 답을 받는 SSE 를 여는 것.
//
// 답을 받는 길은 셋이고 모두 바로 SSE 로 답한다(메시지: turn, expression, delta, done 또는 failed. 읽기는 chatTurns.ts).
//   - 말 보내기  POST /conversations/{id}/messages {content}
//   - 다시 생성  POST /messages/{id}/regenerate
//   - 이어서     POST /messages/{id}/continue
// 답을 시작하기 전의 거절(chat-server/app/turns/router.py 의 머리말):
//   - 409 model_required(모델을 먼저 고른다), 409 generation_in_progress(다른 답을 쓰는 중)
//   - 402 credit_short, gold_required: 사람의 말은 저장했다(message_id). 422 model_unavailable
//   - 422 not_regenerable, not_continuable, 404 message_not_found
//   - 429 too_many_attempts(retry_after), 503 billing_unavailable, provider_unavailable(사람의 말은 저장했다)
// 모델 바꾸기와 대안 고르기는 답을 쓰는 중이면 409 generation_in_progress, 고를 수 없는 모델이면 422 model_unavailable 이다.

import { apiRequest, apiStream } from './http';
import type { ChatModelList, ConversationDetail, ConversationModel } from './types';

const CHAT = '/api/v1/chat';

export function fetchConversation(id: string, signal?: AbortSignal): Promise<ConversationDetail> {
  return apiRequest<ConversationDetail>(`${CHAT}/conversations/${encodeURIComponent(id)}`, signal ? { signal } : {});
}

/** 대화에 고를 수 있는 모델과 말 한 번의 값. free 면 결제 서버 없이 도는 서버라 값이 없다 */
export function fetchChatModels(signal?: AbortSignal): Promise<ChatModelList> {
  return apiRequest<ChatModelList>(`${CHAT}/models`, signal ? { signal } : {});
}

export function chooseConversationModel(id: string, model: string): Promise<ConversationModel> {
  return apiRequest<ConversationModel>(`${CHAT}/conversations/${encodeURIComponent(id)}/model`, { method: 'PUT', body: { model } });
}

/** 다른 대안을 본다. 그 말 아래에서 가장 나중에 생긴 말이 가지의 끝이 된다. 바뀐 대화를 돌려준다 */
export function chooseBranch(id: string, messageId: string): Promise<ConversationDetail> {
  return apiRequest<ConversationDetail>(`${CHAT}/conversations/${encodeURIComponent(id)}/branch`, { method: 'PUT', body: { message_id: messageId } });
}

/** 모델을 부르는 것을 멈춘다. 받은 만큼 저장한다. 멈출 것이 없으면 404 generation_not_running */
export function stopGeneration(generationId: string): Promise<void> {
  return apiRequest<void>(`${CHAT}/generations/${encodeURIComponent(generationId)}/stop`, { method: 'POST' });
}

export function openMessageTurn(id: string, content: string, signal: AbortSignal): Promise<Response> {
  return apiStream(`${CHAT}/conversations/${encodeURIComponent(id)}/messages`, { method: 'POST', body: { content }, signal });
}

export function openRegenerateTurn(messageId: string, signal: AbortSignal): Promise<Response> {
  return apiStream(`${CHAT}/messages/${encodeURIComponent(messageId)}/regenerate`, { method: 'POST', signal });
}

export function openContinueTurn(messageId: string, signal: AbortSignal): Promise<Response> {
  return apiStream(`${CHAT}/messages/${encodeURIComponent(messageId)}/continue`, { method: 'POST', signal });
}
