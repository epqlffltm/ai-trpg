// web/apps/web/src/pages/story/StoryNotesPanel.tsx
// 장면(D2)의 기억(Stitch 22번의 왼쪽 열 창). 펼친 동안만 읽는다. 이 세션에서 인물들이 늘 기억하는 것(기억 메모)을 보고 더하고 고치고 지운다. 요약이 제안한 메모는 받아들이거나 버린다.
// 앞부분의 요약은 읽기만 한다.
// 다음 말부터 모델에 가고 청구하지 않는다. 답을 받는 중에도 고칠 수 있다. 창의 몸은 chat 의 기억 창과 같다(NotesPanel).

import { NotesPanel } from '../chat/conversation/NotesDialog';
import { useStoryNotes } from './useStoryNotes';

export function StoryNotesPanel({ sessionId }: { sessionId: string }) {
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
