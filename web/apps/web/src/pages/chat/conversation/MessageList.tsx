// web/apps/web/src/pages/chat/conversation/MessageList.tsx
// 대사창(C3 의 아래). 시작 상황, 지금 가지의 말들, 흘러 들어오는 답. 새 글이 오면 끝으로 내린다.
// 끝의 말에 할 수 있는 일(답 받기, 다시 생성, 이어서)은 여기 둔다. 답을 받는 중에는 모두 막는다.
// 장면 그림(#983)은 말마다 그 말의 것만 넘긴다.

import { Button } from '@ai-trpg/ui';
import { useEffect, useRef } from 'react';
import type { ConversationDetail, ConversationMessage } from '../../../api/types';
import { speakerName, tailActions } from './conversationView';
import { MessageItem } from './MessageItem';
import { snapshotsOf } from './snapshotsView';
import type { TurnState } from './turnState';
import type { SnapshotsSource } from './useSnapshots';
import { visibleMessages } from './visibleMessages';

type Props = {
  detail: ConversationDetail;
  turn: TurnState | null;
  busy: boolean;
  onBranch: (messageId: string) => void;
  onRegenerate: (messageId: string) => void;
  onContinue: (messageId: string) => void;
  onEdit: (message: ConversationMessage, content: string) => Promise<boolean>;
  /** 책갈피를 단 말들과 달고 떼기(#982) */
  marked: ReadonlySet<string>;
  onBookmark: (message: ConversationMessage) => void;
  /** 장면 그림들과 그리기(#983) */
  snapshots: SnapshotsSource;
};

export function MessageList({ detail, turn, busy, onBranch, onRegenerate, onContinue, onEdit, marked, onBookmark, snapshots }: Props) {
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
          <MessageItem
            key={item.message.id}
            message={item.message}
            detail={detail}
            streaming={item.streaming}
            busy={busy}
            onBranch={onBranch}
            onEdit={onEdit}
            marked={marked.has(item.message.id)}
            onBookmark={onBookmark}
            snapshots={snapshotsOf(snapshots.list, item.message.id)}
            drawPrice={snapshots.price}
            drawBlocked={snapshots.blocked}
            onDraw={(messageId) => snapshots.draw.mutate(messageId)}
          />
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

function TailActions({ detail, busy, onRegenerate, onContinue }: Omit<Props, 'turn' | 'onBranch' | 'onEdit' | 'marked' | 'onBookmark' | 'snapshots'>) {
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
