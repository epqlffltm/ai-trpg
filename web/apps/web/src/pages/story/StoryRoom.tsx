// web/apps/web/src/pages/story/StoryRoom.tsx
// 장면(D2)의 화면. 위에 머리(세계관, 날짜·시간대·장소, 모델)와 장면의 인물, 아래에 대사창과 말 쓰기.
// 한 세션에 한 생성이다. 받는 중이면 보내기, 다시 생성, 대안, 모델 바꾸기를 막는다. 모델이 없으면 보내기 전에 고르게 한다.
// 끝난 세션(엔딩을 봤고 후일담이 없다)은 말 쓰기를 숨긴다. 가지와 다시 생성(엔딩 장면을 다시 쓰기)은 된다.
// 행동(이동, 시간, 선택지, 고백, 건네기)과 답 고치기는 다음 조각에서 더한다.

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import { chooseStoryBranch, openStoryMessageTurn, openStoryRegenerateTurn, type StorySession } from '../../api/story';
import { Composer } from '../chat/conversation/Composer';
import { describeChangeProblem } from '../chat/conversation/turnProblem';
import { TurnNotice } from '../chat/conversation/TurnNotice';
import { StoryHeader } from './StoryHeader';
import { StoryMessageList } from './StoryMessageList';
import { StoryModelDialog } from './StoryModelDialog';
import { storySessionKey } from './storyQueries';
import { sceneOf } from './storyView';
import { castName, isEnded } from './storyWorld';
import type { StoryTurnOpener, useStoryTurn } from './useStoryTurn';

type Props = { session: StorySession; turns: ReturnType<typeof useStoryTurn> };

export function StoryRoom({ session, turns }: Props) {
  const branching = useBranch(session.id);
  const [draft, setDraft] = useState('');
  const [choosingModel, setChoosingModel] = useState(false);
  const closeModel = useCallback(() => setChoosingModel(false), []);
  const streaming = turns.turn !== null;
  const busy = streaming || branching.isPending;
  const scene = sceneOf(session.state, turns.turn);
  const ended = isEnded(session.world.document, scene.state);

  /** 답을 받는다. 모델이 없으면 고르기를 열고 보내지 않는다. 서버가 받아들였으면 true */
  async function answer(open: StoryTurnOpener): Promise<boolean> {
    if (session.model?.usable !== true) {
      setChoosingModel(true);
      return false;
    }
    return turns.run(open);
  }

  async function send() {
    const content = draft;
    if (session.model?.usable === true) setDraft('');
    const taken = await answer((signal) => openStoryMessageTurn(session.id, content, signal));
    if (!taken) setDraft((current) => current || content);
  }

  return (
    <main className="page conversation story">
      <StoryHeader session={session} state={scene.state} busy={busy} onChooseModel={() => setChoosingModel(true)} />
      <section className="story-cast" aria-label="장면의 인물">
        {scene.cast.length === 0 ? <p className="hint">이 장면에는 아무도 없습니다.</p> : null}
        <ul className="plain-list story-cast__list">
          {scene.cast.map((id) => (
            <li key={id} className="story-cast__member">
              {castName(session.world.document, id)}
            </li>
          ))}
        </ul>
      </section>
      <StoryMessageList
        session={session}
        turn={turns.turn}
        busy={busy}
        onBranch={(messageId) => branching.mutate(messageId)}
        onRegenerate={(messageId) => void answer((signal) => openStoryRegenerateTurn(messageId, signal))}
      />
      {branching.error ? <p className="ui-field__error">{describeChangeProblem(branching.error)}</p> : null}
      <TurnNotice problem={turns.problem} failure={turns.failure} onChooseModel={() => setChoosingModel(true)} onClose={turns.clearNotice} />
      {ended ? (
        <p className="hint story-ended">이야기가 끝났습니다. 대안을 넘겨 보거나 끝의 장면을 다시 쓸 수 있습니다.</p>
      ) : (
        <Composer
          draft={draft}
          onDraft={setDraft}
          suggestions={[]}
          streaming={streaming}
          disabled={busy}
          canStop={Boolean(turns.turn?.generationId)}
          onSend={() => void send()}
          onStop={() => void turns.stop()}
        />
      )}
      <StoryModelDialog session={session} open={choosingModel} onClose={closeModel} />
    </main>
  );
}

/** 다른 대안을 본다. 바뀐 세션을 그대로 받아 넣는다 */
function useBranch(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) => chooseStoryBranch(sessionId, messageId),
    onSuccess: (session) => queryClient.setQueryData(storySessionKey(sessionId), session),
  });
}
