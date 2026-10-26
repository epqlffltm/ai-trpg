// web/apps/web/src/pages/chat/conversation/notesView.ts
// 기억 창(C5)의 글과 나눔. 순수한 함수다.
// 받아들인 메모(모델에 가는 것)와 요약이 제안한 것(받아들이기를 기다리는 것)을 나눠 보인다. 스물은 받아들인 것만 센다.

import { ApiError, NetworkError } from '../../../api/errors';
import { NOTE_MAX, NOTES_MAX, type MemoryNote } from '../../../api/chatNotes';

export function splitNotes(notes: MemoryNote[]): { kept: MemoryNote[]; suggested: MemoryNote[] } {
  return { kept: notes.filter((note) => !note.pending), suggested: notes.filter((note) => note.pending) };
}

/** "3 / 20" */
export function notesCountLabel(kept: MemoryNote[]): string {
  return `${kept.length} / ${NOTES_MAX}`;
}

/** 받아들인 것이 스물이면 더하거나 받아들일 수 없다 */
export function notesFull(kept: MemoryNote[]): boolean {
  return kept.length >= NOTES_MAX;
}

/** 쓸 수 있는 메모의 글인가. 빈칸이 아닌 글자가 있고 300자까지 */
export function noteHint(text: string): string | undefined {
  if (!/\S/.test(text)) return '메모를 적어 주세요.';
  if (text.length > NOTE_MAX) return `${NOTE_MAX}자까지입니다.`;
  return undefined;
}

export function sourceLabel(note: MemoryNote): string {
  return note.source === 'summary' ? '요약이 제안' : '내가 씀';
}

export function noteProblemText(error: unknown): string {
  if (error instanceof NetworkError) return '서버에 닿지 못했습니다. 연결을 확인하고 다시 시도하세요.';
  if (!(error instanceof ApiError)) return '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';
  if (error.code === 'notes_full') return `기억 메모는 ${NOTES_MAX}개까지입니다. 지우고 더해 주세요.`;
  if (error.code === 'note_not_found') return '없거나 지운 메모입니다. 목록을 새로 읽습니다.';
  if (error.code === 'too_many_attempts') return `너무 자주 고쳤습니다.${error.retryAfter ? ` ${error.retryAfter}초 뒤에` : ' 잠시 뒤에'} 다시 해 주세요.`;
  if (error.status === 422) return Object.values(error.fields)[0]?.[0] ?? '메모를 확인해 주세요.';
  return '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';
}
