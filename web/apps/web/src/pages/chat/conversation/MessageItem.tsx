// web/apps/web/src/pages/chat/conversation/MessageItem.tsx
// 대사창의 말 하나. 말한 이, 글, 끊긴 답·고친 말의 표시, 받아들인 변화(호감도, 받은 물건, 함께 간 곳), 대안 사이 넘기기("< 2/3 >").
// 행동 말(이동, 건네기)은 이름 없이 서버가 쓴 글 그대로 보인다.
// 고치기: 내 말은 새 가지로 고쳐 보내고(답을 다시 받는다, 청구), 상대의 말은 그 자리에서 고친다(청구 없음, "고침" 표시).
// 행동 말은 서버가 쓴 글이라 고치지 않는다. 받는 중에는 고치지 못한다.

import { Button } from '@ai-trpg/ui';
import { useState } from 'react';
import type { ConversationDetail, ConversationMessage } from '../../../api/types';
import { alternativeView, changeLines, speakerName } from './conversationView';
import { MessageEditor } from './MessageEditor';

type Props = {
  message: ConversationMessage;
  detail: ConversationDetail;
  streaming: boolean;
  busy: boolean;
  onBranch: (messageId: string) => void;
  /** 고친 글을 보낸다. 받아들여졌으면 true(편집 칸을 닫는다) */
  onEdit: (message: ConversationMessage, content: string) => Promise<boolean>;
};

export function MessageItem({ message, detail, streaming, busy, onBranch, onEdit }: Props) {
  const [editing, setEditing] = useState(false);
  const speaker = speakerName(message.role, detail);
  const changes = changeLines(message.changes ?? [], detail.character.document);
  const editable = message.role !== 'action' && !streaming;

  async function submit(content: string) {
    if (await onEdit(message, content)) setEditing(false);
  }

  return (
    <li className={`chat-message chat-message--${message.role}`} aria-busy={streaming || undefined}>
      {speaker ? <p className="chat-message__speaker">{speaker}</p> : null}
      {editing ? (
        <MessageEditor message={message} busy={busy} onSubmit={(content) => void submit(content)} onCancel={() => setEditing(false)} />
      ) : (
        <p className="chat-message__content">{message.content}</p>
      )}
      <MessageMarks message={message} streaming={streaming} />
      {changes.length > 0 ? (
        <ul className="chat-message__changes" aria-label="바뀐 것">
          {changes.map((line, index) => (
            <li key={index}>{line}</li>
          ))}
        </ul>
      ) : null}
      <div className="chat-message__tools">
        {streaming ? null : <Alternatives message={message} busy={busy} onBranch={onBranch} />}
        {editable && !editing ? (
          <Button variant="quiet" disabled={busy} aria-label={`${speaker ?? ''}의 말 고치기`} onClick={() => setEditing(true)}>
            고치기
          </Button>
        ) : null}
      </div>
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
