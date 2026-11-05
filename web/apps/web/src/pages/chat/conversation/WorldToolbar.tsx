// web/apps/web/src/pages/chat/conversation/WorldToolbar.tsx
// 그림 창 아래의 단추들(C3): 책갈피와 그림으로 저장(#982), 시간 보내기, 기록 받기. 창은 겹쳐 연다.
// 지도·소지품·차림·기억은 왼쪽 열의 창(ChatTools)으로 옮겼다(Stitch 21번).
// 시간 보내기는 반응을 받으므로 받는 중이면 막는다. 창을 여는 것과 기록 받기는 막지 않는다.
// 시간 보내기는 다음 시간대가 시작하는 시각까지 흐른다(밤이면 다음 날 새벽 4시).

import { Button } from '@ai-trpg/ui';
import { useCallback, useState } from 'react';
import type { ConversationAction, ConversationDetail } from '../../../api/types';
import { BookmarksDialog } from './BookmarksDialog';
import { ChatTranscriptButton } from './ChatTranscriptButton';
import { ScreenshotDialog } from './ScreenshotDialog';
import { chatShotItems, shotSubtitle } from './screenshotView';
import type { BookmarksSource } from './useBookmarks';
import { genreName, isGenreValue } from '../../../genres/genres';

type Window = 'bookmarks' | 'screenshot' | null;
type Props = {
  detail: ConversationDetail;
  busy: boolean;
  onAction: (action: ConversationAction) => void;
  bookmarks: BookmarksSource;
  /** 책갈피의 자리로 간다 */
  onGoTo: (messageId: string) => void;
};

export function WorldToolbar({ detail, busy, onAction, bookmarks, onGoTo }: Props) {
  const [open, setOpen] = useState<Window>(null);
  // 창(Dialog)은 onClose 가 바뀌면 닫기 단추에 초점을 다시 둔다. 초점이 튀지 않게 고정한다
  const close = useCallback(() => setOpen(null), []);

  function act(action: ConversationAction) {
    setOpen(null);
    onAction(action);
  }

  return (
    <div className="chat-toolbar" role="toolbar" aria-label="창과 행동">
      <Button variant="secondary" onClick={() => setOpen('bookmarks')}>
        책갈피
      </Button>
      <Button variant="secondary" onClick={() => setOpen('screenshot')}>
        그림으로 저장
      </Button>
      <Button variant="secondary" disabled={busy} onClick={() => act({ kind: 'wait' })}>
        시간 보내기
      </Button>
      <ChatTranscriptButton conversationId={detail.id} title={detail.title} />
      <BookmarksDialog source={bookmarks} open={open === 'bookmarks'} busy={busy} onClose={close} onGo={onGoTo} />
      <ScreenshotDialog
        title={detail.character.document.name}
        subtitle={shotSubtitle(isGenreValue(detail.character.document.genre) ? genreName(detail.character.document.genre) : null, detail.character.rating === 'adult')}
        items={chatShotItems(detail)}
        imageId={detail.character.document.image_id ?? null}
        open={open === 'screenshot'}
        onClose={close}
      />
    </div>
  );
}
