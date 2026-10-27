// web/apps/web/src/api/story.ts
// story 서버(D, #591). 세션(세계관 하나를 걷는 한 번), 모델, 말 보내기·행동·다시 생성(바로 SSE), 멈추기, 가지 고르기.
//
// 세션을 시작하면 세계관의 마지막 판을 가져와 고정한다. 모델을 보내지 않으면 지난번 세션의 모델이다(쓸 수 없으면 없이).
// 세션 읽기에는 보여도 되는 세계관의 칸(view), 지금 가지의 말(말마다 대안 alternatives), 그 끝의 상태(state)가 실린다.
// world 는 목록과 같은 요약이다(판의 문서는 싣지 않는다). 화면은 view 만 쓴다. state.affection 에는 호감도를 보이는 인물의 값만 실린다.
// 목록의 줄에는 진행(progress: 날짜, 엔딩, 후일담)이 실린다. 다 쓴 답에는 다음 답 추천(suggestions, 최대 셋)이 실린다.
// 답의 SSE: turn{generation_id, user_message, cast, state}, segment{speaker}, delta{text}, done{message}, failed{code}. 읽기는 chatTurns.ts.
// 답을 시작하기 전의 거절(story-server/app/turns/router.py):
//   - 409 model_required, generation_in_progress, session_ended(끝을 고른 세계관의 엔딩 뒤). 422 model_unavailable, not_regenerable,
//     not_continuable(이어 쓸 수 없는 답), not_editable(사람의 말이 아닌 것을 edit_of 로 고침, 답이 아닌 것을 PATCH)
// 답 고치기(PATCH)의 거절: 422 segments_mismatch(조각의 수가 다르다), 409 generation_in_progress
//   - 402 credit_short, gold_required, 503: 사람의 말은 저장했다(message_id). 404 message_not_found
// 행동(이동, 시간 보내기, 하루 마치기, 선택지, 고백, 건네기)은 엔진이 판정하고 같은 SSE 로 반응을 받는다. 할 수 없으면 422 이고
// 아무것도 저장하지 않는다(cannot_move, no_choice, over, not_in_scene, not_confessable, cooling_down, not_held).
// 세션 시작의 거절: 404 world_not_found, 403 adult_content_required, 503 asset_unavailable(Retry-After). 422 model_unavailable, 503 prices_unavailable.
// 타입은 생성 타입(generated/story)에서 바로 가져온다.

import type { components } from './generated/story';
import { apiRequest, apiStream } from './http';

type Schemas = components['schemas'];
export type StoryModelList = Schemas['ModelList'];
export type StoryModel = Schemas['ModelOut'];
export type StorySessionModel = Schemas['ConversationModelOut'];
export type StorySessionPage = Schemas['ConversationPage'];
export type StorySessionSummary = Schemas['ConversationSummary'];
export type StorySession = Schemas['ConversationDetail'];
export type StoryMessage = Schemas['PathMessageOut'];
export type StorySavedMessage = Schemas['MessageOut'];
export type StorySegment = Schemas['SegmentOut'];
export type StoryState = Schemas['StateOut'];
export type StoryEndingRecords = Schemas['EndingRecordList'];
/** 세션에서 화면이 쓰는 세계관의 칸(보여도 되는 것만, 이 가지에 맞춘 것) */
export type StoryView = Schemas['WorldView'];
export type StoryViewCast = Schemas['CastOut'];
export type StoryProgress = Schemas['ProgressOut'];
export type StoryAction =
  | Schemas['MoveAction']
  | Schemas['PassTimeAction']
  | Schemas['EndDayAction']
  | Schemas['ChooseAction']
  | Schemas['ConfessAction']
  | Schemas['GiveAction'];

const STORY = '/api/v1/story';

/** 한 쪽의 세션 수 */
export const SESSION_PAGE_SIZE = 20;

function withSignal(signal?: AbortSignal) {
  return signal ? { signal } : {};
}

export function fetchStoryModels(signal?: AbortSignal): Promise<StoryModelList> {
  return apiRequest<StoryModelList>(`${STORY}/models`, withSignal(signal));
}

/** 내 세션. 최근의 것부터. worldId 를 주면 그 세계관의 것만 */
export function fetchStorySessions(offset: number, signal?: AbortSignal, worldId?: string): Promise<StorySessionPage> {
  return apiRequest<StorySessionPage>(`${STORY}/conversations`, { query: { limit: SESSION_PAGE_SIZE, offset, world_id: worldId }, ...withSignal(signal) });
}

/** 세계관의 마지막 판으로 새 세션. 모델을 비우면 지난번 세션의 모델이다 */
export function startStorySession(worldId: string): Promise<StorySession> {
  return apiRequest<StorySession>(`${STORY}/conversations`, { method: 'POST', body: { world_id: worldId } });
}

export function fetchStorySession(id: string, signal?: AbortSignal): Promise<StorySession> {
  return apiRequest<StorySession>(`${STORY}/conversations/${encodeURIComponent(id)}`, withSignal(signal));
}

export function chooseStoryModel(id: string, model: string): Promise<StorySessionModel> {
  return apiRequest<StorySessionModel>(`${STORY}/conversations/${encodeURIComponent(id)}/model`, { method: 'PUT', body: { model } });
}

/** 대안을 본다. 그 말 아래에서 가장 나중에 생긴 말이 가지의 끝이 된다. 바뀐 세션을 돌려준다 */
export function chooseStoryBranch(id: string, messageId: string): Promise<StorySession> {
  return apiRequest<StorySession>(`${STORY}/conversations/${encodeURIComponent(id)}/branch`, { method: 'PUT', body: { message_id: messageId } });
}

export function stopStoryGeneration(generationId: string): Promise<void> {
  return apiRequest<void>(`${STORY}/generations/${encodeURIComponent(generationId)}/stop`, { method: 'POST' });
}

/** 말 보내기. editOf 가 있으면 그 내 말을 고친 새 가지다(원본은 대안으로 남는다) */
export function openStoryMessageTurn(id: string, content: string, signal: AbortSignal, editOf?: string): Promise<Response> {
  const body = editOf ? { content, edit_of: editOf } : { content };
  return apiStream(`${STORY}/conversations/${encodeURIComponent(id)}/messages`, { method: 'POST', body, signal });
}

/** 끊긴 답(partial)에 이어 쓴다. turn 에 continues 가 실리고, 첫 segment 앞의 글은 그 답의 마지막 조각에 붙는다 */
export function openStoryContinueTurn(messageId: string, signal: AbortSignal): Promise<Response> {
  return apiStream(`${STORY}/messages/${encodeURIComponent(messageId)}/continue`, { method: 'POST', signal });
}

/** 답을 조각마다 글만 고친다(말하는 사람과 조각의 수는 그대로, 한 줄씩). 청구하지 않는다 */
export function editStoryAnswer(messageId: string, segments: string[]): Promise<StorySavedMessage> {
  return apiRequest<StorySavedMessage>(`${STORY}/messages/${encodeURIComponent(messageId)}`, { method: 'PATCH', body: { segments } });
}

/** 답이면 그 부모에 새 대안을, 답을 못 받은 사람의 말이면 그 말에 답한다 */
export function openStoryRegenerateTurn(messageId: string, signal: AbortSignal): Promise<Response> {
  return apiStream(`${STORY}/messages/${encodeURIComponent(messageId)}/regenerate`, { method: 'POST', signal });
}

/** 행동 하나. 엔진이 판정하고 반응을 흘려보낸다 */
export function openStoryActionTurn(id: string, action: StoryAction, signal: AbortSignal): Promise<Response> {
  return apiStream(`${STORY}/conversations/${encodeURIComponent(id)}/actions`, { method: 'POST', body: action, signal });
}

/** 그 세계관에서 내가 본 엔딩들(처음 본 차례). 세션을 지워도 남는다 */
export function fetchStoryEndings(worldId: string, signal?: AbortSignal): Promise<StoryEndingRecords> {
  return apiRequest<StoryEndingRecords>(`${STORY}/endings`, { query: { world_id: worldId }, ...withSignal(signal) });
}
