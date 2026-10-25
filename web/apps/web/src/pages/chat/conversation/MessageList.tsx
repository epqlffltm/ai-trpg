// web/apps/web/src/pages/chat/conversation/MessageList.tsx
// 대사창(C3 의 아래). 시작 상황, 지금 가지의 말들, 흘러 들어오는 답. 새 글이 오면 끝으로 내린다.
// 끝의 말에 할 수 있는 일(답 받기, 다시 생성, 이어서)은 여기 둔다. 답을 받는 중에는 모두 막는다.

import { Button } from '@ai-trpg/ui';
import { useEffect, useRef } from 'react';
import type { ConversationDetail, ConversationMessage } from '../../../api/types';
import { speakerName, tailActions } from './conversationView';
import { MessageItem } from './MessageItem';
import type { TurnState } from './turnState';
import { visibleMessages } from './visibleMessages';

type Props = {
  detail: ConversationDetail;
  turn: TurnState | null;
  busy: boolean;
  onBranch: (messageId: string) => void;
  onRegenerate: (messageId: string) => void;
  onContinue: (messageId: string) => void;
  onEdit: (message: ConversationMessage, content: string) => Promise<boolean>;
};

export function MessageList({ detail, turn, busy, onBranch, onRegenerate, onContinue, onEdit }: Props) {
  const { items, pending } = visibleMessages(detail.messages, turn);
  const end = useRef<HTMLDivElement>(null);
  const growth = items.length + (pending?.length ?? 0) + (turn?.text.length ?? 0);
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'end' });
  }, [growth]);

  return (
    <section className="conversation__log" aria-label="대화">
      <div className="chat-start">
        <p className="chat-start__title">{detail.start.title}</p>
        <p className="chat-message__content">{detail.start.situation}</p>
      </div>
      <ol className="plain-list chat-messages" aria-label="말">
        {items.map((item) => (
          <MessageItem key={item.message.id} message={item.message} detail={detail} streaming={item.streaming} busy={busy} onBranch={onBranch} onEdit={onEdit} />
        ))}
        {pending !== null ? (
          <li className="chat-message chat-message--assistant" aria-busy="true">
            <p className="chat-message__speaker">{speakerName('assistant', detail)}</p>
            <p className="chat-message__content">{pending || '…'}</p>
            <p className="hint chat-message__marks">쓰는 중</p>
          </li>
        ) : null}
      </ol>
      {turn ? null : <TailActions detail={detail} busy={busy} onRegenerate={onRegenerate} onContinue={onContinue} />}
      <div ref={end} />
    </section>
  );
}

function TailActions({ detail, busy, onRegenerate, onContinue }: Omit<Props, 'turn' | 'onBranch' | 'onEdit'>) {
  const actions = tailActions(detail.messages);
  if (!actions.answer && !actions.regenerate && !actions.continueFrom) return null;
  return (
    <div className="chat-tail">
      {actions.answer ? (
        <Button variant="secondary" disabled={busy} onClick={() => onRegenerate(actions.answer as string)}>
          답 받기
        </Button>
      ) : null}
      {actions.continueFrom ? (
        <Button variant="secondary" disabled={busy} onClick={() => onContinue(actions.continueFrom as string)}>
          이어서
        </Button>
      ) : null}
      {actions.regenerate ? (
        <Button variant="quiet" disabled={busy} onClick={() => onRegenerate(actions.regenerate as string)}>
          다시 생성
        </Button>
      ) : null}
    </div>
  );
}
