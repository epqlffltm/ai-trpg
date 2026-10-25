// web/apps/web/src/pages/chat/conversation/ConversationRoom.tsx
// 대화(C3)의 화면. 위에 머리와 그림 창, 아래에 대사창과 말 쓰기. 모델 고르기는 창으로 연다.
// 한 대화에 한 생성이다. 이 화면이 받는 중이거나(turn) 다른 곳에서 쓰는 중이면(generating) 보내기, 다시 생성, 이어서, 대안을 막는다.
// 모델이 없으면 보내기 전에 고르게 한다(서버의 409 model_required 를 기다리지 않는다).

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { chooseBranch, openContinueTurn, openMessageTurn, openRegenerateTurn } from '../../../api/chatConversation';
import type { ConversationDetail } from '../../../api/types';
import { Composer } from './Composer';
import { ConversationHeader } from './ConversationHeader';
import { conversationKey } from './conversationQueries';
import { pictureOf, tailSuggestions } from './conversationView';
import { MessageList } from './MessageList';
import { ModelDialog } from './ModelDialog';
import { PicturePane } from './PicturePane';
import { describeChangeProblem } from './turnProblem';
import { TurnNotice } from './TurnNotice';
import type { useConversationTurn } from './useConversationTurn';

type Props = { detail: ConversationDetail; turns: ReturnType<typeof useConversationTurn> };

export function ConversationRoom({ detail, turns }: Props) {
  const branching = useBranch(detail.id);
  const [draft, setDraft] = useState('');
  const [choosingModel, setChoosingModel] = useState(false);
  const streaming = turns.turn !== null;
  const busy = streaming || detail.generating || branching.isPending;
  const modelReady = detail.model?.usable === true;
  const picture = pictureOf(detail, turns.turn ? { answering: turns.turn.userMessage, sprite: turns.turn.sprite } : null);

  async function send() {
    if (!modelReady) {
      setChoosingModel(true);
      return;
    }
    const content = draft;
    setDraft('');
    const taken = await turns.run((signal) => openMessageTurn(detail.id, content, signal));
    if (!taken) setDraft((current) => current || content);
  }

  return (
    <main className="page conversation">
      <ConversationHeader detail={detail} busy={busy} onChooseModel={() => setChoosingModel(true)} />
      <PicturePane picture={picture} name={detail.character.document.name} />
      <MessageList
        detail={detail}
        turn={turns.turn}
        busy={busy}
        onBranch={(messageId) => branching.mutate(messageId)}
        onRegenerate={(messageId) => void turns.run((signal) => openRegenerateTurn(messageId, signal))}
        onContinue={(messageId) => void turns.run((signal) => openContinueTurn(messageId, signal))}
      />
      {detail.generating && !streaming ? <p className="hint">답을 쓰는 중입니다. 끝나면 보입니다.</p> : null}
      {branching.error ? <p className="ui-field__error">{describeChangeProblem(branching.error)}</p> : null}
      <TurnNotice problem={turns.problem} failure={turns.failure} onChooseModel={() => setChoosingModel(true)} onClose={turns.clearNotice} />
      <Composer
        draft={draft}
        onDraft={setDraft}
        suggestions={tailSuggestions(detail.messages)}
        streaming={streaming}
        disabled={busy}
        canStop={Boolean(turns.turn?.generationId)}
        onSend={() => void send()}
        onStop={() => void turns.stop()}
      />
      <ModelDialog detail={detail} open={choosingModel} onClose={() => setChoosingModel(false)} />
    </main>
  );
}

/** 다른 대안을 본다. 바뀐 대화를 그대로 받아 넣는다 */
function useBranch(conversationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) => chooseBranch(conversationId, messageId),
    onSuccess: (detail) => queryClient.setQueryData(conversationKey(conversationId), detail),
  });
}
