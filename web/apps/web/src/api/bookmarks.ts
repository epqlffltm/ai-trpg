// web/apps/web/src/api/bookmarks.ts
// 말의 책갈피(#982). chat 의 대화와 story 의 세션이 같은 모양이다. 모델을 부르지 않아 청구하지 않고 답을 받는 중에도 된다.
//   - 말 하나에 하나. 다시 달면 메모만 바뀐다(PUT). 떼기는 달지 않았어도 204 다
//   - 목록은 나중에 단 것부터, 그 말의 역할과 앞부분(excerpt)이 실린다. 그 자리로 가는 것은 가지 고르기(branch)다
// 실패: 409 bookmarks_full(대화마다 100개), 404 message_not_found(그 대화의 말이 아니다), 404(남의 대화), 422(메모 100자 넘음)

import type { components as Chat } from './generated/chat';
import type { components as Story } from './generated/story';
import { apiRequest } from './http';

export type BookmarkService = 'chat' | 'story';
export type Bookmark = Chat['schemas']['BookmarkOut'] | Story['schemas']['BookmarkOut'];

/** 메모의 글자 수와 대화 하나의 책갈피 수의 상한(서버와 같다) */
export const BOOKMARK_NOTE_MAX = 100;
export const BOOKMARKS_MAX = 100;

function bookmarksPath(service: BookmarkService, conversationId: string, messageId?: string): string {
  const base = `/api/v1/${service}/conversations/${encodeURIComponent(conversationId)}/bookmarks`;
  return messageId === undefined ? base : `${base}/${encodeURIComponent(messageId)}`;
}

export function fetchBookmarks(service: BookmarkService, conversationId: string, signal?: AbortSignal): Promise<Bookmark[]> {
  return apiRequest<Bookmark[]>(bookmarksPath(service, conversationId), signal ? { signal } : {});
}

/** 책갈피를 단다. 이미 있으면 메모만 바꾼다. 빈 메모는 메모가 없는 것이다 */
export function putBookmark(service: BookmarkService, conversationId: string, messageId: string, note = ''): Promise<Bookmark> {
  return apiRequest<Bookmark>(bookmarksPath(service, conversationId, messageId), { method: 'PUT', body: { note } });
}

export function removeBookmark(service: BookmarkService, conversationId: string, messageId: string): Promise<void> {
  return apiRequest<void>(bookmarksPath(service, conversationId, messageId), { method: 'DELETE' });
}
