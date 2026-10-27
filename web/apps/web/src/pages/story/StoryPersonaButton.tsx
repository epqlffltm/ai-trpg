// web/apps/web/src/pages/story/StoryPersonaButton.tsx
// 장면(D2)의 "나"(페르소나). 머리에 지금 페르소나의 이름과 "바꾸기". 창에서 내 페르소나 가운데 하나나 "페르소나 없이"를 골라 바꾼다(다음 말부터).
// 같은 페르소나여도 내 목록의 판(revision)이 세션에 가져온 판보다 크면 "새 설정으로 바꾸기"를 보인다(같은 id 를 다시 보낸다).
// 바꾸면 세션의 페르소나 칸만 바꾼다. 404 persona_not_found 면 세션은 그대로라고 알린다. 받는 중에는 막는다.

import { Button, Dialog, Notice } from '@ai-trpg/ui';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import { changeStoryPersona, type StorySession } from '../../api/story';
import { PersonaSelect, usePersonaList } from '../personas/PersonaSelect';
import { personaLabel, staleRevision } from './storyPersonaView';
import { storySessionKey } from './storyQueries';
import { describePersonaProblem } from './storyTurnProblem';

type Props = { session: StorySession; disabled: boolean };

export function StoryPersonaButton({ session, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  return (
    <>
      <p className="hint">나: {personaLabel(session.persona)}</p>
      <Button variant="quiet" disabled={disabled} onClick={() => setOpen(true)}>
        페르소나 바꾸기
      </Button>
      <Dialog title="나(페르소나)" open={open} onClose={close}>
        {open ? <PersonaChoice session={session} onDone={close} /> : null}
      </Dialog>
    </>
  );
}

function PersonaChoice({ session, onDone }: { session: StorySession; onDone: () => void }) {
  const personas = usePersonaList(true);
  const current = session.persona?.id ?? null;
  const [chosen, setChosen] = useState<string | null>(current);
  const changing = usePersonaChange(session.id, onDone);
  const stale = staleRevision(personas, session.persona);
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        changing.mutate(chosen);
      }}
    >
      <p className="hint">지금: {personaLabel(session.persona)}. 바꾸면 다음 말부터 그 설정으로 씁니다.</p>
      <PersonaSelect personas={personas} value={chosen} onChange={setChosen} hint="이야기 속 나의 설정입니다. 지금의 설정을 복사해 둡니다." />
      {changing.error ? <Notice tone="error">{describePersonaProblem(changing.error)}</Notice> : null}
      <div className="actions">
        <Button type="submit" busy={changing.isPending} disabled={chosen === current}>
          이 페르소나로 바꾸기
        </Button>
        {stale && chosen === current ? (
          <Button variant="secondary" busy={changing.isPending} onClick={() => changing.mutate(current)}>
            새 설정으로 바꾸기
          </Button>
        ) : null}
      </div>
      {stale && chosen === current ? <p className="hint">이 페르소나의 설정이 세션을 시작한 뒤에 바뀌었습니다.</p> : null}
    </form>
  );
}

/** 세션의 페르소나를 바꾼다. 세션의 페르소나 칸만 바꿔 다시 읽지 않는다 */
function usePersonaChange(sessionId: string, onDone: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (personaId: string | null) => changeStoryPersona(sessionId, personaId),
    onSuccess: ({ persona }) => {
      queryClient.setQueryData(storySessionKey(sessionId), (session: StorySession | undefined) => (session ? { ...session, persona } : session));
      onDone();
    },
  });
}
