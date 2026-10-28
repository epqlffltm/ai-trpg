// web/apps/web/src/pages/story/StoryNotesButton.tsx
// 장면(D2)의 기억 창. 이 세션에서 인물들이 늘 기억하는 것(기억 메모)을 보고 더하고 고치고 지운다. 앞부분의 요약은 읽기만 한다.
// 다음 말부터 모델에 가고 청구하지 않는다. 답을 받는 중에도 고칠 수 있다. 창의 몸은 chat 의 기억 창과 같다(NotesPanel).

import { Button, Dialog } from '@ai-trpg/ui';
import { useCallback, useState } from 'react';
import { NotesPanel } from '../chat/conversation/NotesDialog';
import { useStoryNotes } from './useStoryNotes';

export function StoryNotesButton({ sessionId }: { sessionId: string }) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        기억
      </Button>
      <Dialog title="기억" open={open} onClose={close}>
        {open ? <StoryNotes sessionId={sessionId} /> : null}
      </Dialog>
    </>
  );
}

function StoryNotes({ sessionId }: { sessionId: string }) {
  const { notes, summary, change } = useStoryNotes(sessionId);
  return (
    <NotesPanel
      name="인물들"
      intro="이 세션에서 인물들이 늘 기억하는 것입니다. 틀린 기억을 바로잡거나 기억할 것을 적습니다. 다음 말부터 들어가고 청구하지 않습니다."
      notes={notes}
      summary={summary}
      change={change}
    />
  );
}
