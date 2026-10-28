// web/apps/web/src/api/storyNotes.ts
// story 의 기억 메모와 굴리는 요약(D2 의 기억 창). 세션마다 하나의 목록이고 가지와 상관없다. 호출이 아니라 청구하지 않는다. 답을 쓰는 중에도 고친다.
//   - 메모는 하나에 300자, 세션 하나에 스물까지. 다음 말부터 모델에 늘 간다. chat 과 달리 요약이 제안하는 메모는 없다
//   - 요약은 읽기만 한다. 아직 없으면 null
// 실패: 409 notes_full, 404 note_not_found(그 세션에 없는 메모), 404(남의 세션), 422(빈 글, 300자 넘음), 429 too_many_attempts

import type { components } from './generated/story';
import { apiRequest } from './http';

export type StoryNote = components['schemas']['NoteOut'];
export type StorySummaryText = components['schemas']['SummaryOut'];

function notesPath(sessionId: string): string {
  return `/api/v1/story/conversations/${encodeURIComponent(sessionId)}/notes`;
}

export function fetchStoryNotes(sessionId: string, signal?: AbortSignal): Promise<StoryNote[]> {
  return apiRequest<StoryNote[]>(notesPath(sessionId), signal ? { signal } : {});
}

export function addStoryNote(sessionId: string, text: string): Promise<StoryNote> {
  return apiRequest<StoryNote>(notesPath(sessionId), { method: 'POST', body: { text } });
}

export function editStoryNote(sessionId: string, noteId: string, text: string): Promise<StoryNote> {
  return apiRequest<StoryNote>(`${notesPath(sessionId)}/${encodeURIComponent(noteId)}`, { method: 'PATCH', body: { text } });
}

export function deleteStoryNote(sessionId: string, noteId: string): Promise<void> {
  return apiRequest<void>(`${notesPath(sessionId)}/${encodeURIComponent(noteId)}`, { method: 'DELETE' });
}

export function fetchStorySummary(sessionId: string, signal?: AbortSignal): Promise<StorySummaryText | null> {
  return apiRequest<StorySummaryText | null>(`/api/v1/story/conversations/${encodeURIComponent(sessionId)}/summary`, signal ? { signal } : {});
}
