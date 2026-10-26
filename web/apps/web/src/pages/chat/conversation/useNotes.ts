// web/apps/web/src/pages/chat/conversation/useNotes.ts
// 기억 창(C5)이 읽고 바꾸는 것. 메모 목록과 요약을 읽고, 더하기·고치기·지우기·받아들이기를 한다. 끝나면 목록을 다시 읽는다.
// 한 번에 하나만 보낸다. 실패하면 목록을 다시 읽는다(다른 탭에서 바뀌었을 수 있다).

import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { acceptNote, addNote, deleteNote, editNote, fetchNotes, fetchSummary } from '../../../api/chatNotes';

export type NoteChange = { kind: 'add'; text: string } | { kind: 'edit'; id: string; text: string } | { kind: 'delete'; id: string } | { kind: 'accept'; id: string };

function notesKey(conversationId: string) {
  return ['chat', 'conversation', conversationId, 'notes'] as const;
}

export function notesQuery(conversationId: string) {
  return queryOptions({ queryKey: notesKey(conversationId), queryFn: ({ signal }) => fetchNotes(conversationId, signal) });
}

export function summaryQuery(conversationId: string) {
  return queryOptions({ queryKey: ['chat', 'conversation', conversationId, 'summary'], queryFn: ({ signal }) => fetchSummary(conversationId, signal) });
}

export function useNotes(conversationId: string, enabled: boolean) {
  const queryClient = useQueryClient();
  const notes = useQuery({ ...notesQuery(conversationId), enabled });
  const summary = useQuery({ ...summaryQuery(conversationId), enabled });
  const change = useMutation({
    mutationFn: (request: NoteChange) => send(conversationId, request),
    onSettled: () => queryClient.invalidateQueries({ queryKey: notesKey(conversationId) }),
  });
  return { notes, summary, change };
}

function send(conversationId: string, request: NoteChange): Promise<unknown> {
  if (request.kind === 'add') return addNote(conversationId, request.text);
  if (request.kind === 'edit') return editNote(conversationId, request.id, request.text);
  if (request.kind === 'accept') return acceptNote(conversationId, request.id);
  return deleteNote(conversationId, request.id);
}
