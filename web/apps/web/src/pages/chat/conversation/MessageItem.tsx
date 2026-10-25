// web/apps/web/src/pages/chat/conversation/MessageItem.tsx
// 대사창의 말 하나. 말한 이, 글, 끊긴 답·고친 말의 표시, 받아들인 변화(호감도, 받은 물건, 함께 간 곳), 대안 사이 넘기기("< 2/3 >").
// 행동 말(이동, 건네기)은 이름 없이 서버가 쓴 글 그대로 보인다.

import { Button } from '@ai-trpg/ui';
import type { ConversationDetail, ConversationMessage } from '../../../api/types';
import { alternativeView, changeLines, speakerName } from './conversationView';

type Props = {
  message: ConversationMessage;
  detail: ConversationDetail;
  streaming: boolean;
  busy: boolean;
  onBranch: (messageId: string) => void;
};

export function MessageItem({ message, detail, streaming, busy, onBranch }: Props) {
  const speaker = speakerName(message.role, detail);
  const changes = changeLines(message.changes ?? [], detail.character.document);
  return (
    <li className={`chat-message chat-message--${message.role}`} aria-busy={streaming || undefined}>
      {speaker ? <p className="chat-message__speaker">{speaker}</p> : null}
      <p className="chat-message__content">{message.content}</p>
      <MessageMarks message={message} streaming={streaming} />
      {changes.length > 0 ? (
        <ul className="chat-message__changes" aria-label="바뀐 것">
          {changes.map((line, index) => (
            <li key={index}>{line}</li>
          ))}
        </ul>
      ) : null}
      {streaming ? null : <Alternatives message={message} busy={busy} onBranch={onBranch} />}
    </li>
  );
}

function MessageMarks({ message, streaming }: { message: ConversationMessage; streaming: boolean }) {
  const marks = [streaming ? '쓰는 중' : null, !streaming && message.status === 'partial' ? '끊긴 답' : null, message.edited ? '고침' : null].filter(Boolean);
  if (marks.length === 0) return null;
  return <p className="hint chat-message__marks">{marks.join(' · ')}</p>;
}

function Alternatives({ message, busy, onBranch }: { message: ConversationMessage; busy: boolean; onBranch: (messageId: string) => void }) {
  const view = alternativeView(message);
  if (!view) return null;
  return (
    <div className="chat-message__alternatives">
      <Button variant="quiet" aria-label="앞의 대안" disabled={busy || !view.previous} onClick={() => view.previous && onBranch(view.previous)}>
        ‹
      </Button>
      <span>
        {view.position}/{view.count}
      </span>
      <Button variant="quiet" aria-label="뒤의 대안" disabled={busy || !view.next} onClick={() => view.next && onBranch(view.next)}>
        ›
      </Button>
    </div>
  );
}
