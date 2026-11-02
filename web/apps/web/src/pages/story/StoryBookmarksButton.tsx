// web/apps/web/src/pages/story/StoryBookmarksButton.tsx
// 장면(D2)의 책갈피 단추와 창(#982). 창의 몸은 chat 의 책갈피 창과 같다(BookmarksDialog).
// 끝난 세션에서도 연다(책갈피로 앞의 가지에 돌아갈 수 있다).

import { Button } from '@ai-trpg/ui';
import { useCallback, useState } from 'react';
import { BookmarksDialog } from '../chat/conversation/BookmarksDialog';
import type { BookmarksSource } from '../chat/conversation/useBookmarks';

type Props = { source: BookmarksSource; busy: boolean; onGoTo: (messageId: string) => void };

export function StoryBookmarksButton({ source, busy, onGoTo }: Props) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        책갈피
      </Button>
      <BookmarksDialog source={source} open={open} busy={busy} onClose={close} onGo={onGoTo} />
    </>
  );
}
