// web/apps/web/src/api/chatNotes.ts
// chat 의 기억 메모와 굴리는 요약(C5). 대화마다 따로 있고 가지와 상관없다. 호출이 아니라 청구하지 않는다. 답을 쓰는 중에도 고친다.
//   - 메모는 하나에 300자, 대화 하나에 스물까지(받아들인 것만 센다). 모델에 늘 간다. 출처는 사용자(user)와 요약의 제안(summary)
//   - 요약이 제안한 메모는 받아들이기 전에는 pending 이고 모델에 가지 않는다. 받아들이기는 accept, 버리기는 지우기다
//   - 요약은 읽기만 한다. 아직 없으면 null
// 실패: 409 notes_full(스물이 가득), 404 note_not_found(그 대화에 없는 메모), 404(남의 대화), 422(빈 글, 300자 넘음), 429 too_many_attempts

import type { components as Chat } from './generated/chat';
import { apiRequest } from './http';

export type MemoryNote = Chat['schemas']['NoteOut'];
export type ConversationSummaryText = Chat['schemas']['SummaryOut'];

/** 하나의 글자 수와 대화 하나의 수의 상한(chat 서버) */
export const NOTE_MAX = 300;
export const NOTES_MAX = 20;

function notesPath(conversationId: string): string {
  return `/api/v1/chat/conversations/${encodeURIComponent(conversationId)}/notes`;
}

export function fetchNotes(conversationId: string, signal?: AbortSignal): Promise<MemoryNote[]> {
  return apiRequest<MemoryNote[]>(notesPath(conversationId), signal ? { signal } : {});
}

export function addNote(conversationId: string, text: string): Promise<MemoryNote> {
  return apiRequest<MemoryNote>(notesPath(conversationId), { method: 'POST', body: { text } });
}

export function editNote(conversationId: string, noteId: string, text: string): Promise<MemoryNote> {
  return apiRequest<MemoryNote>(`${notesPath(conversationId)}/${encodeURIComponent(noteId)}`, { method: 'PATCH', body: { text } });
}

export function deleteNote(conversationId: string, noteId: string): Promise<void> {
  return apiRequest<void>(`${notesPath(conversationId)}/${encodeURIComponent(noteId)}`, { method: 'DELETE' });
}

export function acceptNote(conversationId: string, noteId: string): Promise<MemoryNote> {
  return apiRequest<MemoryNote>(`${notesPath(conversationId)}/${encodeURIComponent(noteId)}/accept`, { method: 'POST' });
}

export function fetchSummary(conversationId: string, signal?: AbortSignal): Promise<ConversationSummaryText | null> {
  return apiRequest<ConversationSummaryText | null>(`/api/v1/chat/conversations/${encodeURIComponent(conversationId)}/summary`, signal ? { signal } : {});
}
