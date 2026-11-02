// web/apps/web/src/pages/chat/conversation/bookmarksView.ts
// 책갈피 창과 단추에 보일 글. 순수한 함수다.

import { ApiError } from '../../../api/errors';
import { BOOKMARKS_MAX, type Bookmark } from '../../../api/bookmarks';

const ROLE_LABELS: Record<string, string> = { user: '내 말', assistant: '답', action: '행동' };

/** 책갈피 한 줄의 앞머리. "답", "내 말", "행동" */
export function bookmarkRoleLabel(bookmark: Bookmark): string {
  return ROLE_LABELS[bookmark.role] ?? bookmark.role;
}

/** "3/100" */
export function bookmarksCountLabel(bookmarks: Bookmark[]): string {
  return `${bookmarks.length}/${BOOKMARKS_MAX}`;
}

/** 책갈피를 바꾸지 못한 까닭 */
export function bookmarkProblemText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'bookmarks_full') return `책갈피가 가득 찼습니다(${BOOKMARKS_MAX}개). 떼고 달아 주세요.`;
    if (error.code === 'message_not_found') return '그 말을 찾지 못했습니다. 대화를 다시 열어 주세요.';
    if (error.status === 422) return '메모는 100자까지 적습니다.';
    if (error.status === 429) return '너무 자주 바꿨습니다. 잠시 뒤에 다시 해 주세요.';
  }
  return '책갈피를 바꾸지 못했습니다. 잠시 뒤에 다시 해 주세요.';
}

/** 그 말이 지금 보는 가지에 있는가. 있으면 가지를 바꾸지 않고 그 자리로 내린다 */
export function isOnBranch(messageIds: string[], messageId: string): boolean {
  return messageIds.includes(messageId);
}

/** 말 하나의 자리(화면의 id). 책갈피로 갈 때 이것으로 찾아 내린다 */
export function messageAnchor(messageId: string): string {
  return `message-${messageId}`;
}
