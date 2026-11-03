// web/apps/web/src/pages/story/StoryScreenshotButton.tsx
// 장면(D2)의 "그림으로 저장"(#982). 지금 가지의 말들 가운데 고른 구간을 그림으로 내려받는다. 창은 chat 과 같다(ScreenshotDialog).

import { Button } from '@ai-trpg/ui';
import { useCallback, useState } from 'react';
import type { StorySession } from '../../api/story';
import { genreName, isGenreValue } from '../../genres/genres';
import { ScreenshotDialog } from '../chat/conversation/ScreenshotDialog';
import { shotSubtitle } from '../chat/conversation/screenshotView';
import { storyShotItems } from './storyShot';

export function StoryScreenshotButton({ session }: { session: StorySession }) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const genre = session.world.genre && isGenreValue(session.world.genre) ? genreName(session.world.genre) : null;
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        그림으로 저장
      </Button>
      <ScreenshotDialog
        title={session.world.name}
        subtitle={shotSubtitle(genre, session.world.rating === 'adult')}
        items={storyShotItems(session.messages, session.view)}
        imageId={session.world.image_id ?? null}
        open={open}
        onClose={close}
      />
    </>
  );
}
