// web/apps/web/src/pages/story/useStoryNotes.ts
// story 의 기억 창이 읽고 바꾸는 것. 메모 목록과 요약을 읽고, 더하기·고치기·지우기를 한다. 끝나면(실패해도) 목록을 다시 읽는다.
// chat 의 기억 창과 같은 모양으로 돌려준다(NotesPanel). story 에는 받아들이기가 없다.

import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { addStoryNote, deleteStoryNote, editStoryNote, fetchStoryNotes, fetchStorySummary } from '../../api/storyNotes';
import type { NoteChange } from '../chat/conversation/useNotes';
import { STORY_KEY } from './storyQueries';

function notesKey(sessionId: string) {
  return [...STORY_KEY, 'session', sessionId, 'notes'] as const;
}

export function storyNotesQuery(sessionId: string) {
  return queryOptions({ queryKey: notesKey(sessionId), queryFn: ({ signal }) => fetchStoryNotes(sessionId, signal) });
}

export function storySummaryQuery(sessionId: string) {
  return queryOptions({ queryKey: [...STORY_KEY, 'session', sessionId, 'summary'], queryFn: ({ signal }) => fetchStorySummary(sessionId, signal) });
}

export function useStoryNotes(sessionId: string) {
  const queryClient = useQueryClient();
  const notes = useQuery(storyNotesQuery(sessionId));
  const summary = useQuery(storySummaryQuery(sessionId));
  const change = useMutation({
    mutationFn: (request: NoteChange) => send(sessionId, request),
    onSettled: () => queryClient.invalidateQueries({ queryKey: notesKey(sessionId) }),
  });
  return { notes, summary, change };
}

function send(sessionId: string, request: NoteChange): Promise<unknown> {
  if (request.kind === 'add') return addStoryNote(sessionId, request.text);
  if (request.kind === 'edit') return editStoryNote(sessionId, request.id, request.text);
  if (request.kind === 'delete') return deleteStoryNote(sessionId, request.id);
  return Promise.reject(new Error('story 의 메모에는 받아들이기가 없다'));
}
