// web/apps/web/src/pages/chat/conversation/useBookmarks.ts
// 말의 책갈피(#982)를 읽고 바꾼다. chat 의 대화와 story 의 장면이 함께 쓴다. 바꾸면 목록을 다시 읽는다.
// 실패하면 목록을 다시 읽는다(다른 탭에서 바뀌었을 수 있다).

import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchBookmarks, putBookmark, removeBookmark, type BookmarkService } from '../../../api/bookmarks';

export type BookmarkChange = { kind: 'put'; messageId: string; note?: string } | { kind: 'remove'; messageId: string };

function bookmarksKey(service: BookmarkService, conversationId: string) {
  return [service, 'conversation', conversationId, 'bookmarks'] as const;
}

export function bookmarksQuery(service: BookmarkService, conversationId: string) {
  return queryOptions({ queryKey: bookmarksKey(service, conversationId), queryFn: ({ signal }) => fetchBookmarks(service, conversationId, signal) });
}

export function useBookmarks(service: BookmarkService, conversationId: string) {
  const queryClient = useQueryClient();
  const bookmarks = useQuery(bookmarksQuery(service, conversationId));
  const change = useMutation({
    mutationFn: (request: BookmarkChange): Promise<unknown> =>
      request.kind === 'put' ? putBookmark(service, conversationId, request.messageId, request.note) : removeBookmark(service, conversationId, request.messageId),
    onSettled: () => queryClient.invalidateQueries({ queryKey: bookmarksKey(service, conversationId) }),
  });
  const marked = new Set((bookmarks.data ?? []).map((bookmark) => bookmark.message_id));
  return { bookmarks, change, marked };
}

export type BookmarksSource = ReturnType<typeof useBookmarks>;
